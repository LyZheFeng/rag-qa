"use client";

import { useEffect, useRef, useState } from "react";
import Markdown from "./Markdown";
import type { AskResponse, Hit } from "@/lib/types";

// 单条助手消息的呈现状态机：
//   retrieving → streaming（sources 已到，delta 逐段追加）→ done（权威终态）| error
// done 前的显示都是临时的；retry 事件清空已显示文本并提示重试中。
export type AssistantState =
  | { phase: "retrieving" }
  | { phase: "streaming"; text: string; hits: Hit[]; retrying: boolean }
  | { phase: "done"; resp: AskResponse }
  | { phase: "error"; message: string; retryQuestion: string };

function Chip({ tone, children }: { tone?: "acc" | "good" | "warn"; children: React.ReactNode }) {
  const cls =
    tone === "acc"
      ? "bg-[var(--acc-soft)] text-[#0b6e64]"
      : tone === "good"
        ? "bg-[#e3f7e9] text-[#177245]"
        : tone === "warn"
          ? "bg-[#fdf1d8] text-[#9a6700]"
          : "bg-[#eef2f5] text-[#4a5b66]";
  return (
    <span className={`inline-block rounded-full px-2.5 py-[3px] text-xs font-semibold ${cls}`}>{children}</span>
  );
}

function CitationCard({ hit, open, onToggle }: { hit: Hit; open: boolean; onToggle: () => void }) {
  return (
    <div id={`cite-${hit.index}`} className="mb-1.5 overflow-hidden rounded-[10px] border border-[var(--line)] border-l-[3px] border-l-[var(--acc)] bg-[#fcfefe]">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[13px] font-semibold text-[#2c4440]"
      >
        <span>
          [{hit.index}] {hit.section_path} · 匹配 {hit.score.toFixed(2)}
        </span>
        <span className={`text-[10px] text-[var(--muted)] transition-transform ${open ? "rotate-180" : ""}`}>▼</span>
      </button>
      {open && (
        <div className="border-t border-[var(--line)] px-3 py-2 text-[13px] leading-relaxed text-[#425651]">
          <span className="mb-1.5 inline-block rounded bg-[#eef2f5] px-1.5 py-0.5 font-mono text-[11px] text-[#4a5b66]">
            {hit.doc_name}
          </span>
          <div className="whitespace-pre-wrap">{hit.text}</div>
        </div>
      )}
    </div>
  );
}

export default function AssistantMessage({
  state,
  onCite,
  onRetry,
}: {
  state: AssistantState;
  onCite: (msgKey: string, index: number) => void;
  onRetry: (question: string) => void;
}) {
  const [openCites, setOpenCites] = useState<Set<number>>(new Set());
  const citeRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (openCites.size > 0) citeRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [openCites]);

  const toggleCite = (n: number) => {
    setOpenCites((prev) => {
      const next = new Set(prev);
      if (next.has(n)) next.delete(n);
      else next.add(n);
      return next;
    });
  };

  if (state.phase === "retrieving") {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--muted)]">
        <span className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--acc)] border-t-transparent" />
        检索 + 生成中…
      </div>
    );
  }

  if (state.phase === "streaming") {
    return (
      <div>
        <Chip tone="acc">已检索 {state.hits.length} 条资料</Chip>
        {state.retrying && <span className="ml-2 align-middle"><Chip tone="warn">输出格式异常 · 正在重试</Chip></span>}
        <div className="mt-2">
          {state.text ? (
            <>
              <Markdown text={state.text} />
              <span className="stream-cursor" />
            </>
          ) : (
            <span className="stream-cursor" />
          )}
        </div>
      </div>
    );
  }

  if (state.phase === "error") {
    return (
      <div>
        <div className="rounded-lg border border-[#fecaca] bg-[#fef2f2] px-3.5 py-2.5 text-sm text-[#b91c1c]">
          {state.message}
        </div>
        <button
          type="button"
          onClick={() => onRetry(state.retryQuestion)}
          className="mt-2 rounded-[10px] border border-[#cfe0dc] bg-white px-3 py-1 text-sm text-[#0b6e64] transition-colors hover:border-[var(--acc)] hover:bg-[var(--acc-soft)]"
        >
          重试
        </button>
      </div>
    );
  }

  // done：权威终态，覆盖一切临时显示
  const { resp } = state;
  const msgKey = `done-${resp.latency.total_ms}-${resp.question.length}`;
  return (
    <div ref={citeRef}>
      {resp.refused && (
        <div className="mb-2 rounded-lg border-l-4 border-[#d97706] bg-[#fdf6e7] px-3 py-2 text-sm text-[#7c5a03]">
          🚫 <b>资料中缺少足够依据，已拒答</b>
        </div>
      )}
      <Markdown
        text={resp.answer}
        onCite={(n) => {
          setOpenCites((prev) => new Set(prev).add(n));
          onCite(msgKey, n);
        }}
      />
      <div className="mt-2 flex flex-wrap gap-1.5">
        <Chip tone="acc">
          引用 {resp.cited.length}/{resp.retrieved.length}
        </Chip>
        <Chip>检索 {resp.latency.retrieve_ms}ms</Chip>
        <Chip>生成 {resp.latency.generate_ms}ms</Chip>
        <Chip>总计 {resp.latency.total_ms}ms</Chip>
        <Chip tone={resp.parse_mode === "json" ? "good" : "warn"}>解析 {resp.parse_mode}</Chip>
      </div>
      {resp.cited.length > 0 && (
        <>
          <div className="mt-3 mb-1 text-[13px] font-bold text-[#33534d]">📖 引用来源 · 点击角标或标题展开 chunk 原文</div>
          {resp.cited.map((h) => (
            <CitationCard key={h.index} hit={h} open={openCites.has(h.index)} onToggle={() => toggleCite(h.index)} />
          ))}
        </>
      )}
    </div>
  );
}
