// rehype 插件：把文本里的 [n] 引用角标替换成 <a href="#cite-n">，
// 由 Markdown 组件映射成可点击的 CitationMark。
// 遍历所有文本节点（含 strong/em 等嵌套内），不依赖额外包。

type Node = {
  type: string;
  tagName?: string;
  properties?: Record<string, unknown>;
  value?: string;
  children?: Node[];
};

function splitText(value: string): Node[] | null {
  if (!/\[\d+\]/.test(value)) return null;
  const out: Node[] = [];
  const re = /\[(\d+)\]/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(value)) !== null) {
    if (m.index > last) out.push({ type: "text", value: value.slice(last, m.index) });
    out.push({
      type: "element",
      tagName: "a",
      properties: { href: `#cite-${m[1]}` },
      children: [],
    });
    last = m.index + m[0].length;
  }
  if (last < value.length) out.push({ type: "text", value: value.slice(last) });
  return out;
}

function walk(node: Node): void {
  if (!node.children) return;
  const replaced: Node[] = [];
  for (const child of node.children) {
    if (child.type === "text" && child.value !== undefined) {
      const parts = splitText(child.value);
      if (parts) {
        replaced.push(...parts);
        continue;
      }
    }
    walk(child);
    replaced.push(child);
  }
  node.children = replaced;
}

export function rehypeCitations() {
  return (tree: Node) => walk(tree);
}
