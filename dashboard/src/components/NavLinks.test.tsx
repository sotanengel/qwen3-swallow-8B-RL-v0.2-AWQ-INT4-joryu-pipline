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
  it("renders exactly 4 navigation items", () => {
    render(<NavLinks />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(4);
    expect(links.map((l) => l.textContent)).toEqual([
      "パイプライン",
      "データ",
      "統計",
      "チャット",
    ]);
  });

  it("marks the pipeline link active on the root path", () => {
    mockUsePathname.mockReturnValue("/");
    render(<NavLinks />);
    const pipeline = screen.getByRole("link", { name: "パイプライン" });
    expect(pipeline.className).toContain("nav-link-active");
    expect(screen.getByRole("link", { name: "チャット" }).className).not.toContain(
      "nav-link-active",
    );
  });

  it("marks the chat link active on the /chat path", () => {
    mockUsePathname.mockReturnValue("/chat");
    render(<NavLinks />);
    expect(screen.getByRole("link", { name: "チャット" }).className).toContain(
      "nav-link-active",
    );
    expect(screen.getByRole("link", { name: "パイプライン" }).className).not.toContain(
      "nav-link-active",
    );
  });

  it("marks the data link active on a nested output detail path", () => {
    mockUsePathname.mockReturnValue("/outputs/abc123");
    render(<NavLinks />);
    expect(screen.getByRole("link", { name: "データ" }).className).toContain(
      "nav-link-active",
    );
  });

  it("marks the stats link active on a stats tab URL", () => {
    mockUsePathname.mockReturnValue("/stats");
    render(<NavLinks />);
    expect(screen.getByRole("link", { name: "統計" }).className).toContain(
      "nav-link-active",
    );
  });
});
