// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RootLayout from "./layout";

vi.mock("@/components/NavLinks", () => ({
  NavLinks: () => <nav data-testid="nav-links" />,
}));

vi.mock("@/components/SystemStatusBar", () => ({
  SystemStatusBar: () => <div data-testid="system-status" />,
}));

vi.mock("@/components/DistillLiveAlertBanner", () => ({
  DistillLiveAlertBanner: () => null,
}));

afterEach(() => {
  cleanup();
});

describe("RootLayout app shell", () => {
  it("renders app-shell structure with main content area", () => {
    const { container } = render(
      <RootLayout>
        <p>page content</p>
      </RootLayout>,
    );

    expect(container.querySelector(".app-shell")).toBeTruthy();
    expect(container.querySelector("main.main")).toBeTruthy();
    expect(screen.getByText("page content")).toBeTruthy();
    expect(screen.getByText("joryu dashboard")).toBeTruthy();
    expect(screen.getByTestId("system-status")).toBeTruthy();
  });
});
