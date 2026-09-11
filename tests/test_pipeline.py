# -*- coding: utf-8 -*-
"""Phase 1 管道单元测试：cleaner 变换 / loader span / chunker 边界与不变量。"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.chunker import HeadingAwareChunker
from pipeline.cleaner import clean_markdown
from pipeline.loader import parse_blocks
from pipeline.models import Doc


def make_docs_src(tmp_path: Path) -> Path:
    root = tmp_path / "docs_src"
    (root / "sec").mkdir(parents=True, exist_ok=True)
    (root / "sec" / "t001.py").write_text("from fastapi import FastAPI\n\napp = FastAPI()\n", encoding="utf-8")
    return root


def clean(text: str, tmp_path: Path) -> str:
    return clean_markdown(text, tmp_path / "x.md", make_docs_src(tmp_path))


# ---------- cleaner ----------

def test_frontmatter_stripped(tmp_path):
    out = clean("---\ninclude_yaml:\n  sponsors: x.yml\n---\n\n# 标题\n\n正文\n", tmp_path)
    assert "include_yaml" not in out and out.startswith("# 标题")


def test_heading_anchor_stripped(tmp_path):
    out = clean("## 效果预览 { #how-it-looks }\n\n正文\n", tmp_path)
    assert "{ #" not in out and out.startswith("## 效果预览")


def test_placeholder_resolved_to_code(tmp_path):
    out = clean("代码：\n\n{* ../../docs_src/sec/t001.py hl[2] *}\n\n完", tmp_path)
    assert "```python" in out and "app = FastAPI()" in out and "{*" not in out


def test_placeholder_unresolved_kept_as_text(tmp_path):
    out = clean("{* ../../fastapi/openapi/docs.py ln[9:24] hl[18:24] *}", tmp_path)
    assert "fastapi/openapi/docs.py" in out  # 保留文字引用


def test_dict_unpack_false_positive_untouched(tmp_path):
    raw = "```python\nnew_dict = {**old_dict, \"new key\": \"new value\"}\n```\n"
    assert clean(raw, tmp_path) == raw


def test_include_resolved_inside_fence(tmp_path):
    raw = "```Python hl_lines=\"1\"\n{!> ../../docs_src/sec/t001.py!}\n```\n"
    out = clean(raw, tmp_path)
    assert "app = FastAPI()" in out and "{!" not in out
    assert "```Python\n" in out  # 围栏语言归一化，剥掉 hl_lines


def test_admonition_to_text_marker(tmp_path):
    raw = "/// warning | 警告\n\n小心。\n\n///\n"
    out = clean(raw, tmp_path)
    assert "⚠️ 警告" in out and "///" not in out and "小心。" in out


def test_tab_syntax(tmp_path):
    raw = "//// tab | Python 3.10+\n\n```python\nx = 1\n```\n\n////\n"
    out = clean(raw, tmp_path)
    assert "【Python 3.10+】" in out and "////" not in out and "x = 1" in out


def test_inline_html_stripped_outside_fence_only(tmp_path):
    raw = (
        "见 <abbr title=\"跨域资源共享\">CORS</abbr> 与 "
        "<img src=\"/img/a.png\" alt=\"界面截图\">。\n\n"
        "<div class=\"termy\">\n\n```console\n$ <font color=\"green\">INFO</font>: ok\n```\n\n</div>\n"
    )
    out = clean(raw, tmp_path)
    assert "CORS（跨域资源共享）" in out
    assert "[图片：界面截图]" in out
    assert "<div" not in out and "</div>" not in out
    assert "INFO" in out  # termy 内代码保留文字、剥掉 font 标签
    assert "$ " in out and "```console" in out


def test_placeholder_multirange_ln_and_title(tmp_path):
    root = make_docs_src(tmp_path)
    (root / "sec" / "lines.py").write_text(
        "\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8"
    )
    raw = '{* ../../docs_src/sec/lines.py ln[1:2,4,9:10] hl[4] title["示例"] *}'
    out = clean(raw, tmp_path)
    assert "line1" in out and "line2" in out and "line4" in out
    assert "line9" in out and "line10" in out and "line3" not in out


def test_long_line_truncated(tmp_path):
    raw = "```python\nimage = \"" + "A" * 3000 + "\"\n```\n"
    out = clean(raw, tmp_path)
    assert len(out) < 700 and "已截断" in out and "AAA" in out


def test_only_github_block_dropped(tmp_path):
    raw = '<div class="only-github" markdown="1">\n\n隐藏内容\n\n</div>\n\n可见\n'
    out = clean(raw, tmp_path)
    assert "隐藏内容" not in out and "可见" in out


# ---------- loader ----------

def build_doc(text: str) -> Doc:
    groups, full_text = parse_blocks(text)
    from pipeline.models import Block

    blocks, cursor = [], 0
    for pid, (path, kind, t) in enumerate(groups, 1):
        if cursor:
            cursor += 2
        blocks.append(Block(pid, path, kind, t, cursor, cursor + len(t)))
        cursor += len(t)
    return Doc(doc_name="t.md", title="t", full_text=full_text, blocks=blocks)


def test_loader_heading_chain_and_spans():
    md = "# 一级\n\n甲段。\n\n## 二级\n\n乙段。\n\n```python\nx = 1\n\ny = 2\n```\n\n丙段。"
    doc = build_doc(md)
    assert [b.heading_path for b in doc.blocks] == [
        ("一级",), ("一级", "二级"), ("一级", "二级"), ("一级", "二级"),
    ]
    assert [b.kind for b in doc.blocks] == ["text", "text", "code", "text"]
    for b in doc.blocks:  # span 精确回切
        assert doc.full_text[b.char_start:b.char_end] == b.text


def test_chunker_invariant_and_boundaries():
    para = "这是一段正文，" * 30  # 180 字符
    md = "# T\n\n" + "\n\n".join([para] * 8) + "\n\n## S2\n\n短段。\n\n```python\n" + "x = 1\n" * 200 + "```\n"
    doc = build_doc(md)
    chunks = HeadingAwareChunker(512, 50).chunk(doc)
    assert chunks, "应产出 chunk"
    for c in chunks:  # 核心不变量
        assert doc.full_text[c.char_start:c.char_end] == c.text
    for c in chunks:
        assert c.n_chars <= 562, f"chunk 超限: {c.n_chars}"  # size + overlap 上界
    # 无跨节：T 节与 S2 节互不混合
    assert {c.section_path for c in chunks} >= {"T", "T > S2"}
    for c in chunks:
        if c.section_path == "T":
            assert "短段" not in c.text and "x = 1" not in c.text
    # 超长代码按行切分且片段可拼回
    code_chunks = [c for c in chunks if c.section_path == "T > S2" and "x = 1" in c.text]
    assert len(code_chunks) >= 2
    # 同节连续 chunk 的 overlap ≥ 0 且不超过 50 字符（首块除外）
    prev = None
    for c in chunks:
        if c.section_path == "T" and prev is not None:
            assert c.text[:20] in prev.text[-60:]  # overlap 尾巴来自上一块
        prev = c


def test_chunker_dedup_within_doc():
    md = "# T\n\n重复内容。\n\n## A\n\n重复内容。\n\n## B\n\n独有。"
    doc = build_doc(md)
    chunks = HeadingAwareChunker(512, 50).chunk(doc)
    assert len([c for c in chunks if c.text == "重复内容。"]) == 1
    ids = [c.chunk_id for c in chunks]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


# ---------- v0.5 FixedChunker ----------

def _make_doc():
    from pipeline.models import Block, Doc

    blocks = [
        Block(1, ("标题一",), "text", "标题一的介绍段落," * 20, 0, 0),
        Block(2, ("标题一", "子节",), "text", "子节内容," * 40, 0, 0),
        Block(3, ("标题二",), "code", "print(1)\n" * 60, 0, 0),
    ]
    full = "\n\n".join(b.text for b in blocks)
    pos = 0
    for b in blocks:
        b.char_start, b.char_end = pos, pos + len(b.text)
        pos += len(b.text) + 2
    return Doc(doc_name="t/x.md", title="X", full_text=full, blocks=blocks)


def test_fixed_chunker_span_invariant_and_size():
    from pipeline.chunker import FixedChunker

    doc = _make_doc()
    chunks = FixedChunker(512, 50).chunk(doc)
    assert len(chunks) > 1
    for c in chunks:
        assert c.text == doc.full_text[c.char_start : c.char_end]
        assert c.n_chars == len(c.text)
    # 常规块不超 size(单行超长除外,本例无超长行)
    assert all(c.n_chars <= 512 for c in chunks)


def test_fixed_chunker_cover_and_overlap():
    from pipeline.chunker import FixedChunker

    doc = _make_doc()
    chunks = FixedChunker(512, 50).chunk(doc)
    assert chunks[0].char_start == 0
    assert chunks[-1].char_end == len(doc.full_text)  # 全覆盖
    for a, b in zip(chunks, chunks[1:]):
        assert b.char_start < a.char_end  # 相邻窗口有重叠
    ids = [c.chunk_id for c in chunks]
    assert ids == [f"t.x#{i:04d}" for i in range(len(chunks))]
