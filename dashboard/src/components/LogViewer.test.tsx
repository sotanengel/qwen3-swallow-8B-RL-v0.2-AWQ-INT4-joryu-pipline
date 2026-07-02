// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LogViewer } from "./LogViewer";

afterEach(() => cleanup());

describe("LogViewer", () => {
  it("shows the empty placeholder when logs are empty", () => {
    render(<LogViewer logs="" />);
    expect(screen.getByTestId("log-viewer").textContent).toBe("(ログなし)");
  });

  it("shows a custom empty label", () => {
    render(<LogViewer logs="" emptyLabel="何もありません" />);
    expect(screen.getByTestId("log-viewer").textContent).toBe("何もありません");
  });

  it("renders the log content", () => {
    render(<LogViewer logs="hello world" />);
    expect(screen.getByTestId("log-viewer").textContent).toBe("hello world");
  });

  it("renders the title heading when provided", () => {
    render(<LogViewer logs="ok" title="ログ" />);
    expect(screen.getByRole("heading", { name: "ログ" })).toBeTruthy();
  });
});
