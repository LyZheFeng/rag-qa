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


class FixedChunker(ChunkStrategy):
    """固定窗口切块(v0.5 对比项):无视标题,按行贪心打包到 size,窗口间保留 ≈overlap 重叠。

    与 HeadingAwareChunker 同样遵守不变量 chunk.text == full_text[char_span];
    超长单行独占一块(与标题策略对超长块的行为一致)。section_path 取窗口首行所在块的标题链。
    """

    def __init__(self, size: int = 512, overlap: int = 50):
        self.size = size
        self.overlap = overlap
        self.name = f"fixed-{size}-{overlap}"

    def chunk(self, doc: Doc) -> list[Chunk]:
        text = doc.full_text
        lines = text.split("\n")
        offsets: list[int] = []
        pos = 0
        for ln in lines:
            offsets.append(pos)
            pos += len(ln) + 1

        def heading_at(line_idx: int) -> str:
            start = offsets[line_idx]
            path: tuple[str, ...] = ()
            for b in doc.blocks:
                if b.char_start <= start:
                    path = b.heading_path
                else:
                    break
            return " > ".join(path) if path else "(无标题)"

        chunks: list[Chunk] = []
        i = 0
        while i < len(lines):
            j, cur = i, len(lines[i])
            while j + 1 < len(lines) and cur + 1 + len(lines[j + 1]) <= self.size:
                j += 1
                cur += 1 + len(lines[j])
            start, end = offsets[i], offsets[j] + len(lines[j])
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.stem}#{len(chunks):04d}",
                    doc_name=doc.doc_name,
                    seq=len(chunks),
                    section_path=heading_at(i),
                    text=text[start:end],
                    char_start=start,
                    char_end=end,
                    n_chars=end - start,
                    hash=text_hash(text[start:end]),
                )
            )
            if end >= len(text):
                break  # 窗口已覆盖到全文末尾,不再回退(否则向末尾收敛出退化窗口)
            # 下一窗口起点:回退到 ≈end-overlap 的行首,至少前进一行
            k = j + 1
            target = end - self.overlap
            while k - 1 > i and offsets[k - 1] >= target:
                k -= 1
            i = k

        seen: set[str] = set()
        unique: list[Chunk] = []
        for c in chunks:
            if c.hash not in seen:
                seen.add(c.hash)
                unique.append(c)
        for n, c in enumerate(unique):
            c.seq = n
            c.chunk_id = f"{doc.stem}#{n:04d}"
        return unique


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
