"""loader：清洗后的 md → Doc（正文块 + 标题链 + 段落号 + 精确 char_span）。

块定义：一个代码围栏整体是一块（kind=code）；其余以空行分段。
char_span 落在 Doc.full_text（各块以 "\n\n" 连接）上，可逐字回溯。
"""

from __future__ import annotations

import re
from pathlib import Path

from .cleaner import clean_markdown
from .models import Block, Doc

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")

# 语料里不是正式文档的文件
EXCLUDE_FILES = {"_llm-test.md", "translation-banner.md"}


def parse_blocks(cleaned: str) -> tuple[list[tuple[tuple[str, ...], str, str]], str]:
    """返回 ([(heading_path, kind, text), ...], full_text)。"""
    groups: list[tuple[tuple[str, ...], str, str]] = []
    heading_stack: list[tuple[int, str]] = []  # (level, title)
    buf: list[str] = []
    buf_kind = "text"
    in_fence = False

    def flush() -> None:
        nonlocal buf, buf_kind
        if not buf:
            return
        text = "\n".join(buf).strip("\n")
        if text.strip():
            path = tuple(t for _, t in heading_stack)
            groups.append((path, buf_kind, text))
        buf, buf_kind = [], "text"

    for line in cleaned.split("\n"):
        stripped = line.strip()
        fence_hit = stripped.startswith("```")
        if in_fence:
            buf.append(line)
            if fence_hit:
                in_fence = False
                flush()
            continue
        if fence_hit:
            flush()
            in_fence = True
            buf_kind = "code"
            buf.append(line)
            continue
        heading = _HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, title))
            continue
        if not stripped:
            flush()
            continue
        buf.append(line)
    flush()

    full_text = "\n\n".join(text for _, _, text in groups)
    return groups, full_text


def load_doc(md_path: Path, corpus_root: Path, docs_src_root: Path) -> Doc:
    rel = md_path.relative_to(corpus_root).as_posix()
    raw = md_path.read_text(encoding="utf-8")
    cleaned = clean_markdown(raw, md_path, docs_src_root)
    groups, full_text = parse_blocks(cleaned)

    blocks: list[Block] = []
    cursor = 0
    for para_id, (path, kind, text) in enumerate(groups, start=1):
        if cursor > 0:
            cursor += 2  # "\n\n" 连接符
        start, end = cursor, cursor + len(text)
        blocks.append(
            Block(
                para_id=para_id,
                heading_path=path,
                kind=kind,
                text=text,
                char_start=start,
                char_end=end,
            )
        )
        cursor = end

    title = groups[0][0][0] if groups and groups[0][0] else rel
    return Doc(doc_name=rel, title=title, full_text=full_text, blocks=blocks)


def iter_corpus(corpus_root: Path) -> list[Path]:
    return sorted(
        p
        for p in corpus_root.rglob("*.md")
        if p.name not in EXCLUDE_FILES and p.parent != corpus_root.parent
    )
