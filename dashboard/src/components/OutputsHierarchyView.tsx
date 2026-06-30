"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo } from "react";

import { DistilledRecord, recordId, recordLooksTruncated, truncateText } from "@/lib/jsonl";
import {
  BROWSE_PAGE_SIZE,
  buildBrowsePath,
  browsePathsEqual,
  parseBrowseParams,
  resolveBrowseState,
} from "@/lib/outputs-browse-url";
import { buildOutputsTree } from "@/lib/outputs-tree";

export { BROWSE_PAGE_SIZE as HIERARCHY_PAGE_SIZE };

function formatTokens(r: DistilledRecord): string {
  const p = r.prompt_tokens;
  const c = r.completion_tokens;
  if (p == null && c == null) return "-";
  return `${p ?? "-"}/${c ?? "-"}`;
}

function formatStatus(r: DistilledRecord): string {
  if (recordLooksTruncated(r)) return "truncated";
  return r.finish_reason ?? "-";
}

function formatLatest(iso: string | null): string {
  if (!iso) return "-";
  return iso.slice(0, 10);
}

interface OutputsHierarchyViewProps {
  records: DistilledRecord[];
  deletingId: string | null;
  onDeleteRecord: (record: DistilledRecord) => void;
}

export function OutputsHierarchyView({
  records,
  deletingId,
  onDeleteRecord,
}: OutputsHierarchyViewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tree = useMemo(() => buildOutputsTree(records), [records]);

  const requested = useMemo(
    () => parseBrowseParams(searchParams),
    [searchParams],
  );

  const resolved = useMemo(
    () => resolveBrowseState(tree, requested),
    [tree, requested],
  );

  const { level, category: selectedCategory, styleId: selectedStyleId, page } = resolved;

  const navigateBrowse = useCallback(
    (state: { category: string | null; styleId: string | null; page: number }) => {
      router.push(buildBrowsePath(state, searchParams));
    },
    [router, searchParams],
  );

  useEffect(() => {
    if (tree.length === 0) return;
    if (!browsePathsEqual(requested, resolved.canonical)) {
      router.replace(buildBrowsePath(resolved.canonical, searchParams));
    }
  }, [tree, requested, resolved, router, searchParams]);

  const selectedCatNode = tree.find((c) => c.category === selectedCategory);
  const selectedStyleNode = selectedCatNode?.styles.find((s) => s.styleId === selectedStyleId);
  const folderRecords = selectedStyleNode?.records ?? [];
  const totalPages = Math.max(1, Math.ceil(folderRecords.length / BROWSE_PAGE_SIZE));
  const pageRecords = folderRecords.slice(
    page * BROWSE_PAGE_SIZE,
    (page + 1) * BROWSE_PAGE_SIZE,
  );

  const goToCategories = () => {
    navigateBrowse({ category: null, styleId: null, page: 0 });
  };

  const goToStyles = (category: string) => {
    navigateBrowse({ category, styleId: null, page: 0 });
  };

  const goToRecords = (category: string, styleId: string) => {
    navigateBrowse({ category, styleId, page: 0 });
  };

  if (tree.length === 0) {
    return <p className="muted">表示する出力がありません。</p>;
  }

  return (
    <>
      <nav className="outputs-breadcrumb" aria-label="フォルダ階層">
        <button type="button" className="outputs-breadcrumb-link" onClick={goToCategories}>
          出力一覧
        </button>
        {selectedCategory ? (
          <>
            <span className="outputs-breadcrumb-sep" aria-hidden="true">
              ›
            </span>
            <button
              type="button"
              className={`outputs-breadcrumb-link${level === "styles" ? " is-current" : ""}`}
              onClick={() => goToStyles(selectedCategory)}
              aria-current={level === "styles" ? "page" : undefined}
            >
              {selectedCategory}
            </button>
          </>
        ) : null}
        {selectedCategory && selectedStyleId ? (
          <>
            <span className="outputs-breadcrumb-sep" aria-hidden="true">
              ›
            </span>
            <span className="outputs-breadcrumb-current" aria-current="page">
              {selectedStyleId}
            </span>
          </>
        ) : null}
      </nav>

      <div className="outputs-folder-panel">
        <div className="outputs-folder-header">
          {level === "categories" ? "category" : null}
          {level === "styles" ? "style_id" : null}
          {level === "records" ? "records" : null}
        </div>

        {level === "categories" ? (
          <div className="outputs-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>名前</th>
                  <th>件数</th>
                  <th>最新</th>
                  <th>trunc</th>
                </tr>
              </thead>
              <tbody>
                {tree.map((cat) => (
                  <tr
                    key={cat.category}
                    className="outputs-hierarchy-row"
                    onClick={() => goToStyles(cat.category)}
                  >
                    <td>
                      <span className="outputs-hierarchy-folder-icon" aria-hidden="true" />
                      {cat.category}
                    </td>
                    <td>{cat.count}</td>
                    <td>{formatLatest(cat.latestCreatedAt)}</td>
                    <td>{cat.truncatedCount > 0 ? cat.truncatedCount : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {level === "styles" && selectedCatNode ? (
          <div className="outputs-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>表示名</th>
                  <th>件数</th>
                  <th>thinking</th>
                </tr>
              </thead>
              <tbody>
                {selectedCatNode.styles.map((style) => (
                  <tr
                    key={style.styleId}
                    className="outputs-hierarchy-row"
                    onClick={() => goToRecords(selectedCategory!, style.styleId)}
                  >
                    <td>
                      <span className="outputs-hierarchy-folder-icon" aria-hidden="true" />
                      {style.styleId}
                    </td>
                    <td>{style.label}</td>
                    <td>{style.count}</td>
                    <td>{style.thinkingCount > 0 ? style.thinkingCount : "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {level === "records" && selectedStyleNode ? (
          <div className="outputs-table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>mode</th>
                  <th>model</th>
                  <th>prompt</th>
                  <th>answer</th>
                  <th>tokens</th>
                  <th>status</th>
                  <th>created_at</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {pageRecords.map((r) => {
                  const id = recordId(r);
                  return (
                    <tr
                      key={id}
                      className="output-list-row"
                      onClick={() => router.push(`/outputs/${id}`)}
                    >
                      <td>{r.mode ?? ""}</td>
                      <td>{r.model ?? "-"}</td>
                      <td>{truncateText(r.prompt, 80)}</td>
                      <td>{truncateText(r.answer, 60)}</td>
                      <td className="cell-nowrap">{formatTokens(r)}</td>
                      <td>
                        {formatStatus(r) === "truncated" ? (
                          <span className="badge-truncated">truncated</span>
                        ) : (
                          formatStatus(r)
                        )}
                      </td>
                      <td className="cell-nowrap">{r.created_at ?? "-"}</td>
                      <td>
                        <button
                          type="button"
                          className="danger-btn"
                          disabled={deletingId === id}
                          onClick={(event) => {
                            event.stopPropagation();
                            onDeleteRecord(r);
                          }}
                        >
                          {deletingId === id ? "削除中…" : "削除"}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>

      {level === "records" && selectedStyleNode && folderRecords.length > BROWSE_PAGE_SIZE ? (
        <div className="pagination">
          <button
            className="secondary-btn"
            onClick={() =>
              navigateBrowse({
                category: selectedCategory!,
                styleId: selectedStyleId!,
                page: Math.max(0, page - 1),
              })
            }
            disabled={page === 0}
          >
            ‹ 前へ
          </button>
          <span className="pagination-meta">
            ページ {page + 1} / {totalPages}
          </span>
          <button
            className="secondary-btn"
            onClick={() =>
              navigateBrowse({
                category: selectedCategory!,
                styleId: selectedStyleId!,
                page: Math.min(totalPages - 1, page + 1),
              })
            }
            disabled={page >= totalPages - 1}
          >
            次へ ›
          </button>
        </div>
      ) : null}
    </>
  );
}
