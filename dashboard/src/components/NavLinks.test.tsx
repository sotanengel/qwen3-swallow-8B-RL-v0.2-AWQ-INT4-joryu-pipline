// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NavLinks } from "./NavLinks";

const mockUsePathname = vi.hoisted(() => vi.fn(() => "/"));

vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    className,
    children,
  }: {
    href: string;
    className?: string;
    children: React.ReactNode;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  mockUsePathname.mockReturnValue("/");
});

describe("NavLinks", () => {
  it("marks home link active on root path", () => {
    mockUsePathname.mockReturnValue("/");
    render(<NavLinks />);
    const home = screen.getByRole("link", { name: "概要" });
    expect(home.className).toContain("nav-link-active");
    expect(screen.getByRole("link", { name: "チャット" }).className).not.toContain(
      "nav-link-active",
    );
  });

  it("marks chat link active on /chat path", () => {
    mockUsePathname.mockReturnValue("/chat");
    render(<NavLinks />);
    expect(screen.getByRole("link", { name: "チャット" }).className).toContain(
      "nav-link-active",
    );
    expect(screen.getByRole("link", { name: "概要" }).className).not.toContain("nav-link-active");
  });

  it("marks outputs link active on nested output detail path", () => {
    mockUsePathname.mockReturnValue("/outputs/abc123");
    render(<NavLinks />);
    expect(screen.getByRole("link", { name: "出力一覧" }).className).toContain("nav-link-active");
  });
});
