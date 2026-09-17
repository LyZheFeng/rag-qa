"use client";

import { useEffect, useState } from "react";
import type { HealthInfo } from "@/lib/types";

const RETRIEVER_LABELS: Record<string, string> = {
  VectorRetriever: "纯向量(v0.1)",
  HybridRetriever: "BM25+向量混合(v0.2)",
  RerankRetriever: "混合+精排(v0.3)",
  RewriteRetriever: "查询改写(v0.4)",
  ParentChildRetriever: "父子块(v0.5)",
};

// 侧栏：/health 轮询（15s）+ 服务状态行 + 清空对话
export default function Sidebar({
  apiBase,
  onClear,
  canClear,
}: {
  apiBase: string;
  onClear: () => void;
  canClear: boolean;
}) {
  const [health, setHealth] = useState<HealthInfo | null>(null);
  const [up, setUp] = useState(false);

  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(5000) });
        if (!r.ok) throw new Error(String(r.status));
        const body = (await r.json()) as HealthInfo;
        if (!alive) return;
        setHealth(body);
        setUp(true);
      } catch {
        if (alive) setUp(false);
      }
    };
    void poll();
    const t = setInterval(poll, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [apiBase]);

  const rows = health
    ? [
        ["检索策略", RETRIEVER_LABELS[health.retriever] ?? health.retriever],
        ["知识库", `${health.chunks.toLocaleString()} chunks`],
        ["嵌入模型", `bge-m3 · ${health.embed_dim} 维`],
        ["生成模型", health.llm_model],
      ]
    : [];

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-white/[.06] bg-[linear-gradient(180deg,#0e312c_0%,#0b2226_100%)] p-4 text-[#cfe3df] md:flex">
      <div className="mb-2 flex items-center text-[15px] font-bold text-white">
        <span
          className={`mr-2 inline-block h-2 w-2 rounded-full ${up ? "bg-[#34d399] shadow-[0_0_6px_rgba(52,211,153,.55)]" : "bg-[#f87171]"}`}
        />
        {up ? "服务在线" : "服务离线"}
      </div>
      {up && rows.length > 0 && (
        <div className="mb-2">
          {rows.map(([k, v]) => (
            <div key={k} className="flex items-baseline justify-between gap-3 border-b border-dashed border-white/[.09] py-1.5 text-[13px]">
              <span className="text-[#9fc0ba]">{k}</span>
              <span className="text-right font-semibold text-white">{v}</span>
            </div>
          ))}
        </div>
      )}
      <div className="my-3 border-t border-white/[.12]" />
      <p className="text-xs leading-relaxed text-[#8fb3ac]">
        💡 想要<b className="text-[#cfe3df]">代码示例</b>就直接问“怎么写/怎么用”；资料没覆盖的问题会收到拒答说明，换个问法或检查关键词往往就能命中。
      </p>
      <button
        type="button"
        onClick={onClear}
        disabled={!canClear}
        className="mt-3 w-full rounded-[10px] border border-white/[.18] bg-white/[.07] px-3 py-1.5 text-sm text-[#e2efec] transition-colors hover:border-[var(--acc)] hover:bg-[rgba(0,150,135,.3)] disabled:cursor-not-allowed disabled:opacity-40"
      >
        🗑 清空对话
      </button>
      <div className="mt-auto pt-4 text-[11px] text-[#6f958d]">
        rag-qa {health ? `v${health.version}` : ""} · 本地运行
      </div>
    </aside>
  );
}
