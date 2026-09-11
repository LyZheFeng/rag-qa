"""v0.5 parent-child:child chunk (256/50) retrieval → map to parent chunk (whole section) → top-k parents.

Motivation: small chunks locate more precisely, big chunks give the generator complete section context.
Parent ids use the "P:" prefix to avoid same-name collisions with child chunk_ids.
"""

from __future__ import annotations

import json

from .schemas import Hit


class ParentChildRetriever:
    """The externally visible Hit is the parent chunk (section-level); the score follows the child's retrieval score."""

    def __init__(self, child, child_to_parent: dict[str, str], parents: dict[str, dict], candidates: int = 20):
        self.child = child
        self.child_to_parent = child_to_parent
        self.parents = parents
        self.candidates = candidates

    def retrieve(self, query: str, k: int = 5) -> list[Hit]:
        child_hits = self.child.retrieve(query, k=self.candidates)
        out: list[Hit] = []
        seen: set[str] = set()
        for h in child_hits:
            pid = self.child_to_parent.get(h.chunk_id)
            if not pid or pid in seen:
                continue
            seen.add(pid)
            p = self.parents[pid]
            out.append(
                Hit(
                    index=len(out) + 1,
                    chunk_id=pid,
                    doc_name=p["doc_name"],
                    section_path=p["section_path"],
                    text=p["text"],
                    score=h.score,
                )
            )
            if len(out) >= k:
                break
        return out


def build_pc_maps(chunks_dir) -> tuple[dict[str, str], dict[str, dict]]:
    """children jsonl + parents jsonl → (child_id→parent_id, parent_id→parent record)。

    映射键 = (doc_name, section_path);父 id 加 "P:" 前缀避免与子 chunk_id 同名冲突。
    """
    children = _load(chunks_dir / "chunks_pc.jsonl")
    parents = _load(chunks_dir / "chunks_pc_parent.jsonl")

    parent_by_key: dict[tuple[str, str], dict] = {}
    parents_by_id: dict[str, dict] = {}
    for p in parents:
        rec = dict(p)
        rec["chunk_id"] = "P:" + p["chunk_id"]
        parent_by_key[(p["doc_name"], p["section_path"])] = rec
        parents_by_id[rec["chunk_id"]] = rec

    child_to_parent: dict[str, str] = {}
    for c in children:
        rec = parent_by_key.get((c["doc_name"], c["section_path"]))
        if rec is not None:
            child_to_parent[c["chunk_id"]] = rec["chunk_id"]
    return child_to_parent, parents_by_id


def _load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
