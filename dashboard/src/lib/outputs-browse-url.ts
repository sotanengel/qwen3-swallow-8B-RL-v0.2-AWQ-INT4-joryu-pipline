import { CategoryNode } from "./outputs-tree";

export type BrowseLevel = "categories" | "styles" | "records";

export const BROWSE_PAGE_SIZE = 25;

export interface BrowseUrlState {
  category: string | null;
  styleId: string | null;
  page: number;
}

export interface ResolvedBrowseState extends BrowseUrlState {
  level: BrowseLevel;
  canonical: BrowseUrlState;
}

const BROWSE_KEYS = ["category", "style_id", "page"] as const;

export function parseBrowseParams(searchParams: URLSearchParams): BrowseUrlState {
  const category = searchParams.get("category");
  const styleId = searchParams.get("style_id");
  const pageRaw = searchParams.get("page");
  let page = 0;
  if (pageRaw) {
    const parsed = Number.parseInt(pageRaw, 10);
    if (Number.isFinite(parsed) && parsed >= 1) {
      page = parsed - 1;
    }
  }
  return {
    category: category || null,
    styleId: styleId || null,
    page,
  };
}

export function buildBrowsePath(
  state: BrowseUrlState,
  preserve?: URLSearchParams,
): string {
  const params = new URLSearchParams(preserve?.toString() ?? "");
  for (const key of BROWSE_KEYS) {
    params.delete(key);
  }
  if (state.category) params.set("category", state.category);
  if (state.styleId) params.set("style_id", state.styleId);
  if (state.page > 0) params.set("page", String(state.page + 1));
  const qs = params.toString();
  return qs ? `/outputs?${qs}` : "/outputs";
}

function findCategory(tree: CategoryNode[], category: string): CategoryNode | undefined {
  return tree.find((node) => node.category === category);
}

function findStyle(cat: CategoryNode, styleId: string) {
  return cat.styles.find((style) => style.styleId === styleId);
}

export function resolveBrowseState(
  tree: CategoryNode[],
  requested: BrowseUrlState,
): ResolvedBrowseState {
  if (!requested.category) {
    return {
      level: "categories",
      category: null,
      styleId: null,
      page: 0,
      canonical: { category: null, styleId: null, page: 0 },
    };
  }

  const catNode = findCategory(tree, requested.category);
  if (!catNode) {
    return {
      level: "categories",
      category: null,
      styleId: null,
      page: 0,
      canonical: { category: null, styleId: null, page: 0 },
    };
  }

  if (!requested.styleId) {
    return {
      level: "styles",
      category: catNode.category,
      styleId: null,
      page: 0,
      canonical: { category: catNode.category, styleId: null, page: 0 },
    };
  }

  const styleNode = findStyle(catNode, requested.styleId);
  if (!styleNode) {
    return {
      level: "styles",
      category: catNode.category,
      styleId: null,
      page: 0,
      canonical: { category: catNode.category, styleId: null, page: 0 },
    };
  }

  const maxPage = Math.max(0, Math.ceil(styleNode.records.length / BROWSE_PAGE_SIZE) - 1);
  const page = Math.min(Math.max(0, requested.page), maxPage);

  return {
    level: "records",
    category: catNode.category,
    styleId: styleNode.styleId,
    page,
    canonical: {
      category: catNode.category,
      styleId: styleNode.styleId,
      page,
    },
  };
}

export function browsePathsEqual(a: BrowseUrlState, b: BrowseUrlState): boolean {
  return a.category === b.category && a.styleId === b.styleId && a.page === b.page;
}
