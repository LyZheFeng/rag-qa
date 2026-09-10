"""清洗 FastAPI 中文 md → 纯净 markdown。

处理项（对应 Phase 0 语料侦察结论）：
- YAML frontmatter 剥离
- `{* path [ln[a:b]] [hl[..]] *}` 占位符 → docs_src 真实代码块（440 处）
- `{!> path !}` / `{! path !}` 包含语法 → 文件原文（出现在代码围栏内）
- 标题自定义锚点 `## 标题 { #anchor }` → 剥离锚点保留文本与层级
- 告示块 `/// type | 标题 ... ///` → `**{icon} 标题**：` 普通文本标记
- 选项卡 `//// tab | X ... ////` → `**【X】**` 标记
- `<div class="only-github">` 整块删除（站点上不渲染）；termy/screenshot 包裹行删除
- 行内 HTML（span/font/b/abbr/img/kbd...）→ 纯文本；仅作用于代码围栏之外
- 代码围栏语言标注归一化（剥掉 hl_lines 等属性）

所有代码文件内容原样进入，不做 HTML 清洗（围栏感知）。
"""

from __future__ import annotations

import re
from pathlib import Path

EXT_LANG = {
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "html": "html",
    "css": "css",
    "sh": "bash",
    "bash": "bash",
    "json": "json",
    "yml": "yaml",
    "yaml": "yaml",
    "sql": "sql",
}

ADMONITION_ICON = {
    "note": "📝",
    "tip": "💡",
    "warning": "⚠️",
    "danger": "‼️",
    "details": "📌",
    "info": "ℹ️",
    "example": "🧪",
    "quote": "❝",
    "check": "✅",
    "question": "❓",
}

# {* path [ln[1:9,29:35]] [hl[..]] [title["..."]] *}：多区间行号与 title 属性都存在；
# 要求 "*}" 结尾且 "{*" 后有空格+路径，避免误伤 `{**dict解包}`
PLACEHOLDER_RE = re.compile(
    r"\{\*\s+(\S+)\s+(?:ln\[([\d:, -]+)\]\s+)?(?:hl\[[\d,: -]+\]\s*)?"
    r'(?:title\["[^"]*"\]\s*)?\*\}'
)
# {! path !} 与 {!> path !}（后者多出现在带语言的围栏内）
INCLUDE_RE = re.compile(r"\{!>?\s*([^\s!]+)\s*!\}")
HEADING_ANCHOR_RE = re.compile(r"^(#{1,6}\s+.+?)\s*\{\s*#[^}]*\}\s*$", re.M)
ADMONITION_OPEN_RE = re.compile(r"^///\s+([a-zA-Z]+)\s*\|\s*(.*?)\s*$")
TAB_OPEN_RE = re.compile(r"^////\s+tab\s*\|\s*(.*?)\s*$")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*(\S*)")
DIV_CLASS_RE = re.compile(r'<div\s+class="([^"]*)"')
IMG_ALT_RE = re.compile(r'<img[^>]*\balt="([^"]*)"[^>]*>')
IMG_RE = re.compile(r"<img[^>]*>")
ABBR_TITLE_RE = re.compile(r'<abbr[^>]*\btitle="([^"]*)"[^>]*>(.*?)</abbr>', re.S)
ABBR_RE = re.compile(r"<abbr[^>]*>(.*?)</abbr>", re.S)
A_RE = re.compile(r"<a\s[^>]*>(.*?)</a>", re.S)
TAG_RE = re.compile(r"</?(?:span|font|b|strong|i|em|u|kbd|dfn|small|sub|sup|mark|s|code|div|p|br)\b[^>]*/?>", re.I)
BR_RE = re.compile(r"<br\s*/?>", re.I)
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
GENERIC_TAG_RE = re.compile(r"</?[a-zA-Z][^>]*>")


def _resolve_docs_src(path_str: str, docs_src_root: Path) -> tuple[str | None, str]:
    """把文档内相对路径映射到本地 docs_src 镜像，返回 (解析结果, 归一化相对名)。"""
    norm = path_str.replace("\\", "/")
    marker = "docs_src/"
    idx = norm.find(marker)
    rel = norm[idx + len(marker):] if idx >= 0 else norm.lstrip("./")
    candidate = docs_src_root / rel
    return (str(candidate) if candidate.is_file() else None), rel


def _fence(lang: str | None, content: str) -> str:
    body = content.rstrip("\n")
    opener = f"```{lang}" if lang else "```"
    return f"{opener}\n{body}\n```"


def clean_markdown(raw: str, md_path: Path, docs_src_root: Path) -> str:
    # 1) frontmatter
    text = re.sub(r"\A---\n.*?\n---\n?", "", raw, count=1, flags=re.S)

    # 2) 标题锚点（围栏外才可能是标题行，锚点语法不会出现在代码里，先全局处理）
    text = HEADING_ANCHOR_RE.sub(r"\1", text)

    lines = text.split("\n")
    out: list[str] = []
    in_fence = False
    skip_until_close_div = False
    stats = {"placeholders_resolved": 0, "includes_resolved": 0, "unresolved": 0}

    for line in lines:
        if skip_until_close_div:
            if "</div>" in line:
                skip_until_close_div = False
            continue

        fence_match = FENCE_RE.match(line)
        if fence_match:
            in_fence = not in_fence
            if in_fence and fence_match.group(2):
                # 语言归一化：剥掉 hl_lines="..." 等属性
                lang = fence_match.group(2)
                line = f"{fence_match.group(1)}{lang}"
            out.append(line)
            continue

        if not in_fence:
            # only-github 块整块删除（站点不渲染）
            div_class = DIV_CLASS_RE.search(line)
            if div_class and "only-github" in div_class.group(1):
                if "</div>" not in line:
                    skip_until_close_div = True
                continue
            # termy / screenshot 等纯包裹 div 行删除，保留内部内容
            if line.strip().startswith("<div") or line.strip() == "</div>":
                continue

        # 占位符与包含语法（围栏内外都可能出现）
        def _sub_placeholder(m: re.Match) -> str:
            resolved, rel = _resolve_docs_src(m.group(1), docs_src_root)
            if resolved is None:
                stats["unresolved"] += 1
                return m.group(0)
            stats["placeholders_resolved"] += 1
            content = Path(resolved).read_text(encoding="utf-8")
            if m.group(2):  # ln[...] 行选择，支持 1:9,29:35 这类多区间
                lines = content.split("\n")
                picked: list[str] = []
                for part in m.group(2).split(","):
                    part = part.strip()
                    if ":" in part:
                        lo, hi = (int(x) for x in part.split(":", 1))
                        picked.extend(lines[lo - 1:hi])
                    elif part:
                        picked.append(lines[int(part) - 1])
                content = "\n".join(picked) + "\n"
            if in_fence:
                return content.rstrip("\n")
            lang = EXT_LANG.get(Path(rel).suffix.lstrip(".").lower())
            return _fence(lang, content)

        def _sub_include(m: re.Match) -> str:
            resolved, rel = _resolve_docs_src(m.group(1), docs_src_root)
            if resolved is None:
                stats["unresolved"] += 1
                return m.group(0)
            stats["includes_resolved"] += 1
            return Path(resolved).read_text(encoding="utf-8").rstrip("\n")

        line = PLACEHOLDER_RE.sub(_sub_placeholder, line)
        line = INCLUDE_RE.sub(_sub_include, line)

        if not in_fence:
            # 告示块开/闭
            adm = ADMONITION_OPEN_RE.match(line)
            if adm:
                icon = ADMONITION_ICON.get(adm.group(1).lower(), "📝")
                title = adm.group(2).strip()
                out.append(f"**{icon} {title}：**" if title else f"**{icon}**：")
                continue
            if line.strip() == "///":
                continue
            # 选项卡
            tab = TAB_OPEN_RE.match(line)
            if tab:
                out.append(f"**【{tab.group(1).strip()}】**")
                continue
            if line.strip() == "////":
                continue
            # 行内 HTML → 文本
            line = IMG_ALT_RE.sub(lambda m: f"[图片：{m.group(1).strip()}]", line)
            line = IMG_RE.sub("[图片]", line)
            line = ABBR_TITLE_RE.sub(lambda m: f"{m.group(2)}（{m.group(1)}）", line)
            line = ABBR_RE.sub(r"\1", line)
            line = A_RE.sub(r"\1", line)
            line = COMMENT_RE.sub("", line)
            line = BR_RE.sub(" ", line)
            line = TAG_RE.sub("", line)
            line = GENERIC_TAG_RE.sub("", line)

        out.append(line)

    def _truncate(l: str) -> str:
        # 超长单行（base64 图片字面量等，含占位符替换注入的内容）统一截断
        return l if len(l) <= 1000 else l[:400] + f"…（超长行已截断，原 {len(l)} 字符）"

    cleaned = "\n".join(_truncate(l) for l in out)
    # 压掉 3 连以上空行为 1 空行
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    LAST_STATS.clear()
    LAST_STATS.update(stats)
    return cleaned


LAST_STATS: dict = {"placeholders_resolved": 0, "includes_resolved": 0, "unresolved": 0}
