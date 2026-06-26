"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { OutputsHierarchyView } from "@/components/OutputsHierarchyView";
import { deleteAllOutputs, deleteOutput } from "@/lib/outputs";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";
import {
  DistilledRecord,
  jsonlDataChanged,
  loadJsonl,
  recordId,
  recordLooksTruncated,
  searchRecords,
  truncateText,
} from "@/lib/jsonl";
import { SearchHit, searchRanked } from "@/lib/search";

const PAGE_SIZE = 25;
type SearchMode = "keyword" | "ranked";

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

export default function OutputsPage() {
  const router = useRouter();
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);
  const fastPoll = useDistillJobFastPoll();
  const records = useIntervalPoll(
    async () => {
      const rows = await loadJsonl();
      setLoaded(true);
      return rows;
    },
    [] as DistilledRecord[],
    { shouldUpdate: jsonlDataChanged, intervalMs: 3000, fastPoll },
  );
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("keyword");
  const [mode, setMode] = useState<"all" | "thinking" | "nothinking">("all");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(0);
  const [rankedHits, setRankedHits] = useState<SearchHit[]>([]);
  const [rankedTotal, setRankedTotal] = useState(0);
  const [rankedLoading, setRankedLoading] = useState(false);
  const [rankedUnavailable, setRankedUnavailable] = useState(false);

  const isSearchActive = query.trim().length > 0;

  const modeFiltered = useMemo(
    () => searchRecords(records, { query: "", mode, category: undefined }),
    [records, mode],
  );

  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const r of records) {
      if (r.category) set.add(r.category);
    }
    return [...set].sort();
  }, [records]);

  const keywordFiltered = useMemo(
    () =>
      searchRecords(records, {
        query,
        mode,
        category: category || undefined,
      }),
    [records, query, mode, category],
  );

  const runRankedSearch = useCallback(async () => {
    if (searchMode !== "ranked") return;
    setRankedLoading(true);
    const result = await searchRanked({
      query,
      mode,
      category,
      limit: PAGE_SIZE,
      offset: page * PAGE_SIZE,
    });
    setRankedLoading(false);
    if (result.index_status === "unavailable") {
      setRankedUnavailable(true);
      setRankedHits([]);
      setRankedTotal(0);
      return;
    }
    setRankedUnavailable(false);
    setRankedHits(result.hits);
    setRankedTotal(result.total);
  }, [searchMode, query, mode, category, page]);

  useEffect(() => {
    if (searchMode !== "ranked") return;
    const timer = setTimeout(() => {
      void runRankedSearch();
    }, 300);
    return () => clearTimeout(timer);
  }, [searchMode, runRankedSearch]);

  useEffect(() => {
    if (rankedUnavailable && searchMode === "ranked") {
      setSearchMode("keyword");
    }
  }, [rankedUnavailable, searchMode]);

  const isRanked = isSearchActive && searchMode === "ranked";
  const totalCount = isRanked ? rankedTotal : keywordFiltered.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const keywordPageRows = keywordFiltered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const displayRows: { record: DistilledRecord; hit?: SearchHit }[] = isRanked
    ? rankedHits.map((hit) => ({ record: hit.record, hit }))
    : keywordPageRows.map((record) => ({ record }));

  const onDeleteOne = async (record: DistilledRecord) => {
    const id = recordId(record);
    if (typeof window !== "undefined" && !window.confirm("この出力を削除しますか？")) {
      return;
    }
    setDeletingId(id);
    setError(null);
    try {
      await deleteOutput(id);
      if (isSearchActive) {
        const nextFilteredLen = totalCount - 1;
        const nextTotalPages = Math.max(1, Math.ceil(nextFilteredLen / PAGE_SIZE));
        if (page >= nextTotalPages) {
          setPage(Math.max(0, nextTotalPages - 1));
        }
        if (isRanked) {
          void runRankedSearch();
        }
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setDeletingId(null);
    }
  };

  const onDeleteAll = async () => {
    if (records.length === 0) return;
    if (
      typeof window !== "undefined" &&
      !window.confirm("すべての出力を削除しますか？この操作は取り消せません。")
    ) {
      return;
    }
    setDeletingAll(true);
    setError(null);
    try {
      await deleteAllOutputs();
      setPage(0);
      if (isRanked) {
        setRankedHits([]);
        setRankedTotal(0);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setDeletingAll(false);
    }
  };

  return (
    <>
      <section className="section">
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "1rem",
            flexWrap: "wrap",
          }}
        >
          <h2 style={{ margin: 0 }}>出力一覧</h2>
          <button
            type="button"
            className="danger-btn"
            disabled={!loaded || records.length === 0 || deletingAll}
            onClick={() => void onDeleteAll()}
          >
            {deletingAll ? "削除中…" : "全削除"}
          </button>
        </div>
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="search-bar">
        <input
          type="search"
          placeholder="prompt / answer / thinking_trace を検索"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPage(0);
          }}
        />
        <select
          value={searchMode}
          onChange={(e) => {
            setSearchMode(e.target.value as SearchMode);
            setPage(0);
          }}
          aria-label="検索モード"
          disabled={!isSearchActive}
          title={!isSearchActive ? "検索クエリ入力時のみ利用可能" : undefined}
        >
          <option value="keyword">keyword</option>
          <option value="ranked">ranked (BM25)</option>
        </select>
        <select
          value={mode}
          onChange={(e) => {
            setMode(e.target.value as typeof mode);
            setPage(0);
          }}
        >
          <option value="all">mode: all</option>
          <option value="thinking">thinking</option>
          <option value="nothinking">nothinking</option>
        </select>
        <select
          value={category}
          onChange={(e) => {
            setCategory(e.target.value);
            setPage(0);
          }}
          disabled={!isSearchActive}
          title={!isSearchActive ? "検索時のみ利用可能（通常閲覧は左列で category を選択）" : undefined}
        >
          <option value="">category: all</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </section>

      {rankedUnavailable ? (
        <p className="search-warning" role="status">
          BM25 検索 API が利用できないため keyword モードに切り替えました。
        </p>
      ) : null}

      {!loaded ? (
        <p style={{ color: "var(--muted)" }}>
          responses.jsonl を読み込み中…
          <br />
          (dashboard/public/responses.jsonl にシンボリックリンクまたはコピーを置いてください)
        </p>
      ) : isSearchActive ? (
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          {isRanked && rankedLoading ? "検索中… " : ""}
          {totalCount.toLocaleString()} / {records.length.toLocaleString()} 件 ヒット (ページ{" "}
          {page + 1} / {totalPages})
        </p>
      ) : (
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          全 {modeFiltered.length.toLocaleString()} 件 — category → style_id → records
        </p>
      )}

      {loaded && !isSearchActive ? (
        <OutputsHierarchyView
          records={modeFiltered}
          deletingId={deletingId}
          onDeleteRecord={(record) => void onDeleteOne(record)}
        />
      ) : null}

      {loaded && isSearchActive ? (
        <>
          <div className="outputs-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>category</th>
                  <th>mode</th>
                  <th>style_id</th>
                  <th>model</th>
                  <th>prompt</th>
                  <th>answer</th>
                  <th>tokens</th>
                  <th>status</th>
                  <th>created_at</th>
                  {isRanked ? (
                    <>
                      <th>score</th>
                      <th>snippet</th>
                    </>
                  ) : null}
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                {displayRows.map(({ record: r, hit }) => {
                  const id = recordId(r);
                  return (
                    <tr
                      key={id}
                      className="output-list-row"
                      onClick={() => router.push(`/outputs/${id}`)}
                    >
                      <td style={{ verticalAlign: "top" }}>{r.category ?? ""}</td>
                      <td style={{ verticalAlign: "top" }}>{r.mode ?? ""}</td>
                      <td style={{ verticalAlign: "top" }}>{r.style_id ?? "-"}</td>
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
                      {isRanked ? (
                        <>
                          <td style={{ verticalAlign: "top", whiteSpace: "nowrap" }}>
                            {hit ? hit.score.toFixed(2) : "-"}
                          </td>
                          <td style={{ verticalAlign: "top", maxWidth: "16rem" }}>
                            {hit?.snippet ? (
                              <pre className="snippet search-snippet">{hit.snippet}</pre>
                            ) : (
                              "-"
                            )}
                          </td>
                        </>
                      ) : null}
                      <td style={{ verticalAlign: "top" }}>
                        <button
                          type="button"
                          className="danger-btn"
                          disabled={deletingId === id}
                          onClick={(event) => {
                            event.stopPropagation();
                            void onDeleteOne(r);
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

          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
              ‹ 前へ
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
            >
              次へ ›
            </button>
          </div>
        </>
      ) : null}
    </>
  );
}
