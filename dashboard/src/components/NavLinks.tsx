"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "パイプライン" },
  { href: "/outputs", label: "データ" },
  { href: "/stats", label: "統計" },
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
