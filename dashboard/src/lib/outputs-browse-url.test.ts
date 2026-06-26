import { describe, expect, it } from "vitest";

import { CategoryNode } from "./outputs-tree";
import {
  buildBrowsePath,
  parseBrowseParams,
  resolveBrowseState,
} from "./outputs-browse-url";

const TREE: CategoryNode[] = [
  {
    category: "国語",
    count: 3,
    truncatedCount: 0,
    latestCreatedAt: "2026-06-01T00:00:00Z",
    styles: [
      {
        styleId: "prose",
        label: "散文",
        count: 2,
        thinkingCount: 1,
        records: [],
      },
      {
        styleId: "dialog",
        label: "対話",
        count: 1,
        thinkingCount: 0,
        records: [],
      },
    ],
  },
  {
    category: "(未分類)",
    count: 1,
    truncatedCount: 0,
    latestCreatedAt: null,
    styles: [
      {
        styleId: "(default)",
        label: "(default)",
        count: 1,
        thinkingCount: 0,
        records: [],
      },
    ],
  },
];

describe("parseBrowseParams", () => {
  it("returns root state when params are empty", () => {
    expect(parseBrowseParams(new URLSearchParams())).toEqual({
      category: null,
      styleId: null,
      page: 0,
    });
  });

  it("parses category, style_id, and 1-based page", () => {
    const params = new URLSearchParams("category=%E5%9B%BD%E8%AA%9E&style_id=prose&page=2");
    expect(parseBrowseParams(params)).toEqual({
      category: "国語",
      styleId: "prose",
      page: 1,
    });
  });

  it("ignores invalid page values", () => {
    expect(parseBrowseParams(new URLSearchParams("page=0"))).toEqual({
      category: null,
      styleId: null,
      page: 0,
    });
    expect(parseBrowseParams(new URLSearchParams("page=abc"))).toEqual({
      category: null,
      styleId: null,
      page: 0,
    });
  });
});

describe("buildBrowsePath", () => {
  it("builds root path", () => {
    expect(buildBrowsePath({ category: null, styleId: null, page: 0 })).toBe("/outputs");
  });

  it("builds category-only path", () => {
    expect(buildBrowsePath({ category: "国語", styleId: null, page: 0 })).toBe(
      "/outputs?category=%E5%9B%BD%E8%AA%9E",
    );
  });

  it("builds full browse path with 1-based page", () => {
    expect(
      buildBrowsePath({ category: "国語", styleId: "prose", page: 1 }, new URLSearchParams("mode=thinking")),
    ).toBe("/outputs?mode=thinking&category=%E5%9B%BD%E8%AA%9E&style_id=prose&page=2");
  });

  it("encodes special folder names", () => {
    expect(
      buildBrowsePath({ category: "(未分類)", styleId: "(default)", page: 0 }),
    ).toBe("/outputs?category=%28%E6%9C%AA%E5%88%86%E9%A1%9E%29&style_id=%28default%29");
  });
});

describe("resolveBrowseState", () => {
  it("resolves categories level at root", () => {
    expect(resolveBrowseState(TREE, { category: null, styleId: null, page: 0 })).toEqual({
      level: "categories",
      category: null,
      styleId: null,
      page: 0,
      canonical: { category: null, styleId: null, page: 0 },
    });
  });

  it("resolves styles level for valid category", () => {
    expect(resolveBrowseState(TREE, { category: "国語", styleId: null, page: 0 })).toEqual({
      level: "styles",
      category: "国語",
      styleId: null,
      page: 0,
      canonical: { category: "国語", styleId: null, page: 0 },
    });
  });

  it("resolves records level for valid category and style", () => {
    expect(resolveBrowseState(TREE, { category: "国語", styleId: "prose", page: 0 })).toEqual({
      level: "records",
      category: "国語",
      styleId: "prose",
      page: 0,
      canonical: { category: "国語", styleId: "prose", page: 0 },
    });
  });

  it("falls back when style_id is invalid", () => {
    expect(resolveBrowseState(TREE, { category: "国語", styleId: "missing", page: 0 })).toEqual({
      level: "styles",
      category: "国語",
      styleId: null,
      page: 0,
      canonical: { category: "国語", styleId: null, page: 0 },
    });
  });

  it("falls back to root when category is invalid", () => {
    expect(resolveBrowseState(TREE, { category: "数学", styleId: "prose", page: 3 })).toEqual({
      level: "categories",
      category: null,
      styleId: null,
      page: 0,
      canonical: { category: null, styleId: null, page: 0 },
    });
  });
});
