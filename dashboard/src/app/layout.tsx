import type { Metadata, Viewport } from "next";
import Link from "next/link";

import { DistillLiveAlertBanner } from "@/components/DistillLiveAlertBanner";

import "./globals.css";

export const metadata: Metadata = {
  title: "joryu dashboard",
  description: "Qwen3-Swallow-8B-RL-v0.2-AWQ-INT4 distillation dashboard",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <header className="topbar">
          <h1>joryu dashboard</h1>
          <nav>
            <Link href="/">概要</Link>
            <Link href="/outputs">出力一覧</Link>
            <Link href="/distributions">分布</Link>
            <Link href="/curation">高品質抽出</Link>
            <Link href="/prompts">プロンプト作成</Link>
            <Link href="/screening">健全性</Link>
            <Link href="/jobs">ジョブ</Link>
            <Link href="/chat">チャット</Link>
          </nav>
        </header>
        <DistillLiveAlertBanner />
        <main className="main">{children}</main>
        <footer className="footer">
          <span>
            stats.json / responses.jsonl を再読み込みします（蒸留中 1 秒、通常 3 秒）。
          </span>
        </footer>
      </body>
    </html>
  );
}
