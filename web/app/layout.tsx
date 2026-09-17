import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "FastAPI 中文文档问答",
  description: "BM25 + 向量混合检索 → Qwen 依据资料作答 · 逐句标注引用 · 资料不足诚实拒答",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="zh-CN" className="h-full antialiased">
      <body className="min-h-full font-sans">{children}</body>
    </html>
  );
}
