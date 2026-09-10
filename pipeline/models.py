"""管道统一中间格式。

Doc.blocks 按原文顺序排列；full_text = 各 block 文本以 "\n\n" 连接，
block.char_start/char_end 是其在 full_text 中的精确区间，
Chunk 的 char_span 同样落在 full_text 上，保证溯源到清洗后的原文。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Block:
    para_id: int  # 文档内从 1 递增的段落号
    heading_path: tuple[str, ...]  # 标题链，如 ("安全 - 第一步", "运行")
    kind: str  # "text" | "code"（code 含完整围栏）
    text: str
    char_start: int
    char_end: int


@dataclass
class Doc:
    doc_name: str  # 仓库内相对路径，如 tutorial/security/first-steps.md
    title: str
    full_text: str
    blocks: list[Block] = field(default_factory=list)

    @property
    def stem(self) -> str:
        return self.doc_name[: -len(".md")].replace("/", ".")


@dataclass
class Chunk:
    chunk_id: str  # "{doc_stem}#{seq:04d}"，确定性 ID，重跑 upsert 幂等
    doc_name: str
    seq: int  # 文档内顺序（0 起）
    section_path: str  # " > ".join(标题链)
    text: str
    char_start: int
    char_end: int
    n_chars: int
    hash: str

    def to_record(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "doc_name": self.doc_name,
            "seq": self.seq,
            "section_path": self.section_path,
            "text": self.text,
            "char_span": [self.char_start, self.char_end],
            "n_chars": self.n_chars,
            "hash": self.hash,
        }

    @classmethod
    def from_record(cls, r: dict) -> "Chunk":
        return cls(
            chunk_id=r["chunk_id"],
            doc_name=r["doc_name"],
            seq=r["seq"],
            section_path=r["section_path"],
            text=r["text"],
            char_start=r["char_span"][0],
            char_end=r["char_span"][1],
            n_chars=r["n_chars"],
            hash=r["hash"],
        )
