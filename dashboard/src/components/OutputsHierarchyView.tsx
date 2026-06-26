"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { DistilledRecord, recordId, recordLooksTruncated, truncateText } from "@/lib/jsonl";
import { buildOutputsTree } from "@/lib/outputs-tree";

export const HIERARCHY_PAGE_SIZE = 25;

export type BrowseLevel = "categories" | "styles" | "records";

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
  const tree = useMemo(() => buildOutputsTree(records), [records]);
  const [level, setLevel] = useState<BrowseLevel>("categories");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedStyleId, setSelectedStyleId] = useState<string | null>(null);
  const [page, setPage] = useState(0);

  const selectedCatNode = tree.find((c) => c.category === selectedCategory);
  const selectedStyleNode = selectedCatNode?.styles.find((s) => s.styleId === selectedStyleId);

  useEffect(() => {
    if (tree.length === 0) {
      setLevel("categories");
      setSelectedCategory(null);
      setSelectedStyleId(null);
      return;
    }
    if (level === "styles" || level === "records") {
      if (!selectedCatNode) {
        setLevel("categories");
        setSelectedCategory(null);
        setSelectedStyleId(null);
        return;
      }
    }
    if (level === "records" && !selectedStyleNode) {
      setLevel("styles");
      setSelectedStyleId(null);
    }
  }, [tree, level, selectedCatNode, selectedStyleNode]);

  const folderRecords = selectedStyleNode?.records ?? [];
  const totalPages = Math.max(1, Math.ceil(folderRecords.length / HIERARCHY_PAGE_SIZE));
  const pageRecords = folderRecords.slice(
    page * HIERARCHY_PAGE_SIZE,
    (page + 1) * HIERARCHY_PAGE_SIZE,
  );

  useEffect(() => {
    setPage(0);
  }, [level, selectedCategory, selectedStyleId]);

  const goToCategories = () => {
    setLevel("categories");
    setSelectedCategory(null);
    setSelectedStyleId(null);
  };

  const goToStyles = (category: string) => {
    setLevel("styles");
    setSelectedCategory(category);
    setSelectedStyleId(null);
  };

  const goToRecords = (category: string, styleId: string) => {
    setLevel("records");
    setSelectedCategory(category);
    setSelectedStyleId(styleId);
  };

  if (tree.length === 0) {
    return <p style={{ color: "var(--muted)" }}>表示する出力がありません。</p>;
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
            <table>
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
            <table>
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
            <table>
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
                      <td style={{ verticalAlign: "top" }}>{r.mode ?? ""}</td>
                      <td style={{ verticalAlign: "top" }}>{r.model ?? "-"}</td>
                      <td>{truncateText(r.prompt, 80)}</td>
                      <td>{truncateText(r.answer, 60)}</td>
                      <td style={{ verticalAlign: "top", whiteSpace: "nowrap" }}>
                        {formatTokens(r)}
                      </td>
                      <td style={{ verticalAlign: "top" }}>
                        {formatStatus(r) === "truncated" ? (
                          <span className="badge-truncated">truncated</span>
                        ) : (
                          formatStatus(r)
                        )}
                      </td>
                      <td style={{ verticalAlign: "top", whiteSpace: "nowrap" }}>
                        {r.created_at ?? "-"}
                      </td>
                      <td style={{ verticalAlign: "top" }}>
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

      {level === "records" && selectedStyleNode && folderRecords.length > HIERARCHY_PAGE_SIZE ? (
        <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
          <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
            ‹ 前へ
          </button>
          <span style={{ color: "var(--muted)", fontSize: "0.9rem", alignSelf: "center" }}>
            ページ {page + 1} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page >= totalPages - 1}
          >
            次へ ›
          </button>
        </div>
      ) : null}
    </>
  );
}
