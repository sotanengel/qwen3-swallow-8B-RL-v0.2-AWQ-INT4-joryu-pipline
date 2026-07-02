// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { JobPanel } from "./JobPanel";

type Row = {
  id: string;
  status: "queued" | "running" | "succeeded" | "cancelled";
  created_at: string;
  finished_at: string | null;
};

const baseProps = {
  jobs: [] as Row[],
  selectedId: null as string | null,
  onSelect: () => {},
  onCancel: () => {},
  logs: "",
};

afterEach(() => cleanup());

describe("JobPanel", () => {
  it("renders the form when title and subtitle are omitted", () => {
    const form = <button type="button">プロンプト作成を実行</button>;
    render(<JobPanel form={form} {...baseProps} />);
    expect(screen.getByRole("button", { name: "プロンプト作成を実行" })).toBeTruthy();
  });

  it("renders title heading and form when title is provided", () => {
    const form = <button type="button">実行</button>;
    render(<JobPanel form={form} title="プロンプト生成" {...baseProps} />);
    expect(screen.getByRole("heading", { name: "プロンプト生成" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "実行" })).toBeTruthy();
  });

  it("renders error banner and form when only error is provided", () => {
    const form = <button type="button">実行</button>;
    render(<JobPanel form={form} error="something went wrong" {...baseProps} />);
    expect(screen.getByText("something went wrong")).toBeTruthy();
    expect(screen.getByRole("button", { name: "実行" })).toBeTruthy();
  });

  it("renders log section when selectedId is set", () => {
    const form = <button type="button">実行</button>;
    render(
      <JobPanel
        form={form}
        {...baseProps}
        selectedId="abcdefgh-1234"
        logs="hello log"
      />,
    );
    expect(screen.getByTestId("log-viewer").textContent).toBe("hello log");
  });
});
