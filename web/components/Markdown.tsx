"use client";

import ReactMarkdown from "react-markdown";
import { rehypeCitations } from "@/lib/rehype-citations";

// 答案渲染：Markdown + [n] 角标替换为可点击引用（a#cite-n 由 CitationMark 呈现）
export default function Markdown({
  text,
  onCite,
}: {
  text: string;
  onCite?: (index: number) => void;
}) {
  return (
    <div className="prose prose-sm max-w-none prose-p:my-1.5 prose-pre:my-2 prose-code:before:content-none prose-code:after:content-none prose-code:rounded prose-code:bg-[#eef2f5] prose-code:px-1 prose-code:py-0.5 prose-code:text-[0.85em] prose-code:font-normal">
      <ReactMarkdown
        rehypePlugins={[rehypeCitations]}
        components={{
          a: ({ href, children }) => {
            const m = /^#cite-(\d+)$/.exec(href ?? "");
            if (m) {
              const n = Number(m[1]);
              return (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    onCite?.(n);
                  }}
                  className="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded-[5px] border border-[#bfe8e1] bg-[var(--acc-soft)] px-1 align-[1px] text-[11px] font-bold text-[#0b6e64] transition-colors hover:border-[var(--acc)] hover:bg-[var(--acc)] hover:text-white"
                  title={`查看引用 [${n}]`}
                >
                  {n}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
