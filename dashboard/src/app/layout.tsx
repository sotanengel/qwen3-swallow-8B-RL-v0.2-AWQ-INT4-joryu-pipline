import type { Metadata, Viewport } from "next";
import Link from "next/link";

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
            <Link href="/search">検索</Link>
            <Link href="/distributions">分布</Link>
            <Link href="/jobs">ジョブ</Link>
          </nav>
        </header>
        <main className="main">{children}</main>
        <footer className="footer">
          <span>stats.json を読み込み中。joryu-stats を実行して更新できます。</span>
        </footer>
      </body>
    </html>
  );
}
