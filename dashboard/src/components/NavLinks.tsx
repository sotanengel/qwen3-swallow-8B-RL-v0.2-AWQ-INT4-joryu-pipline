"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "概要" },
  { href: "/outputs", label: "出力一覧" },
  { href: "/distributions", label: "分布" },
  { href: "/curation", label: "高品質抽出" },
  { href: "/prompts", label: "プロンプト作成" },
  { href: "/screening", label: "健全性" },
  { href: "/jobs", label: "ジョブ" },
  { href: "/chat", label: "チャット" },
] as const;

function isActive(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function NavLinks() {
  const pathname = usePathname();

  return (
    <nav>
      {NAV_ITEMS.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className={`nav-link${isActive(pathname, item.href) ? " nav-link-active" : ""}`}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
