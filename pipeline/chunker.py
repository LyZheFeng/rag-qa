"""chunker：策略接口 + 基线实现「标题感知 512/50」。

不变量：chunk.text 严格等于 doc.full_text[char_start:char_end]，
Phase 5 引用高亮可直接用 char_span 切原文。

规则：
- 标题路径变化即开新组，块永不跨标题组合
- 组内贪心打包到 size（字符数），溢出时保留 overlap 字符尾巴滚动
- 超长单块（如整文件代码）按行切成 ≤ size 的片段，不切断行；
  同块的相邻片段在 full_text 中以 "\\n" 相接，跨块以 "\\n\\n" 相接
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Chunk, Doc, text_hash


class ChunkStrategy(ABC):
    name: str = "base"

    @abstractmethod
    def chunk(self, doc: Doc) -> list[Chunk]: ...


class Unit:
    """打包原子：单块，或超长块切出的一片（均携带 full_text 偏移）。"""

    __slots__ = ("text", "start", "end", "same_block_prev")

    def __init__(self, text: str, start: int, end: int, same_block_prev: bool):
        self.text, self.start, self.end = text, start, end
        self.same_block_prev = same_block_prev


def _joiner(u: Unit) -> str:
    """u 与其前一个单元在 full_text 中的真实间隔。"""
    return "\n" if u.same_block_prev else "\n\n"


class HeadingAwareChunker(ChunkStrategy):
    def __init__(self, size: int = 512, overlap: int = 50):
        self.size = size
        self.overlap = overlap
        self.name = f"heading-{size}-{overlap}"

    def _split_oversized(self, text: str, start: int) -> list[Unit]:
        """按行切超长块；片段以 "\\n" 相接可精确还原原文。"""
        units: list[Unit] = []
        lines = text.split("\n")
        offsets: list[int] = []
        pos = start
        for ln in lines:
            offsets.append(pos)
            pos += len(ln) + 1
        cur: list[str] = []
        cur_start = offsets[0]
        first = True
        for ln, off in zip(lines, offsets):
            if cur and len("\n".join(cur + [ln])) > self.size:
                piece = "\n".join(cur)
                units.append(Unit(piece, cur_start, cur_start + len(piece), not first))
                first = False
                cur, cur_start = [ln], off
            else:
                cur.append(ln)
        if cur:
            piece = "\n".join(cur)
            units.append(Unit(piece, cur_start, cur_start + len(piece), not first))
        return units

    def chunk(self, doc: Doc) -> list[Chunk]:
        chunks: list[Chunk] = []
        seq = 0
        blocks = doc.blocks
        i = 0
        while i < len(blocks):
            # 同一标题路径的连续块为一节
            section = blocks[i].heading_path
            j = i
            while j < len(blocks) and blocks[j].heading_path == section:
                j += 1
            section_blocks = blocks[i:j]
            i = j

            units: list[Unit] = []
            for b in section_blocks:
                if len(b.text) <= self.size:
                    units.append(Unit(b.text, b.char_start, b.char_end, False))
                else:
                    units.extend(self._split_oversized(b.text, b.char_start))

            packed: list[Unit] = []
            cur_text = ""
            for u in units:
                joiner = _joiner(u) if packed else ""
                if packed and len(cur_text + joiner + u.text) > self.size:
                    chunks.append(self._make(doc, section, seq, packed, cur_text))
                    seq += 1
                    tail = cur_text[-self.overlap:].lstrip()
                    if tail and u.text:
                        tail_start = packed[-1].end - len(tail)
                        packed = [Unit(tail, tail_start, packed[-1].end, False)]
                        cur_text = tail
                        joiner = _joiner(u)
                        if len(cur_text + joiner + u.text) > self.size:
                            packed, cur_text, joiner = [], "", ""
                    else:
                        packed, cur_text, joiner = [], "", ""
                packed.append(u)
                cur_text += joiner + u.text
            if packed:
                chunks.append(self._make(doc, section, seq, packed, cur_text))
                seq += 1

        # 文档内按内容 hash 去重（跨文档不去重，保留各自上下文）
        seen: set[str] = set()
        unique: list[Chunk] = []
        for c in chunks:
            if c.hash not in seen:
                seen.add(c.hash)
                unique.append(c)
        for k, c in enumerate(unique):  # seq 重排保证连续
            c.seq = k
            c.chunk_id = f"{doc.stem}#{k:04d}"
        return unique

    def _make(
        self,
        doc: Doc,
        section: tuple[str, ...],
        seq: int,
        packed: list[Unit],
        text: str,
    ) -> Chunk:
        return Chunk(
            chunk_id=f"{doc.stem}#{seq:04d}",
            doc_name=doc.doc_name,
            seq=seq,
            section_path=" > ".join(section),
            text=text,
            char_start=packed[0].start,
            char_end=packed[-1].end,
            n_chars=len(text),
            hash=text_hash(text),
        )
