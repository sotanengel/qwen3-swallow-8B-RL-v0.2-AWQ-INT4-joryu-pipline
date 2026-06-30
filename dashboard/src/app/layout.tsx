import type { Metadata, Viewport } from "next";

import { DistillLiveAlertBanner } from "@/components/DistillLiveAlertBanner";
import { NavLinks } from "@/components/NavLinks";
import { SystemStatusBar } from "@/components/SystemStatusBar";

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
        <div className="app-shell">
          <header className="topbar">
            <h1>joryu dashboard</h1>
            <NavLinks />
          </header>
          <SystemStatusBar />
          <DistillLiveAlertBanner />
          <main className="main">{children}</main>
          <footer className="footer">
            <span>
              stats.json / responses.jsonl を再読み込みします（蒸留中 1 秒、通常 3 秒）。
            </span>
          </footer>
        </div>
      </body>
    </html>
  );
}
