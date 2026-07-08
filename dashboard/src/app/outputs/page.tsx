"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";

import { OutputsHierarchyView } from "@/components/OutputsHierarchyView";
import { downloadJsonl } from "@/lib/download";
import { deleteAllOutputs, deleteOutput } from "@/lib/outputs";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";
import {
  DistilledRecord,
  jsonlDataChanged,
  loadCuratedJsonl,
  loadJsonl,
  recordId,
  recordLooksTruncated,
  searchRecords,
  truncateText,
} from "@/lib/jsonl";
import { SearchHit, searchRanked } from "@/lib/search";

const PAGE_SIZE = 25;
type SearchMode = "keyword" | "ranked";
type OutputDataset = "distilled" | "extracted";

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

function parseDataset(value: string | null): OutputDataset {
  return value === "extracted" ? "extracted" : "distilled";
}

export default function OutputsPage() {
  return (
    <Suspense fallback={<p className="muted">出力一覧を読み込み中…</p>}>
      <OutputsPageContent />
    </Suspense>
  );
}

function OutputsPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialCategory = searchParams.get("category") ?? "";
  const dataset = parseDataset(searchParams.get("dataset"));
  const [loaded, setLoaded] = useState(false);
  const [curatedLoaded, setCuratedLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deletingAll, setDeletingAll] = useState(false);
  const fastPoll = useDistillJobFastPoll();
  const distilledRecords = useIntervalPoll(
    async () => {
      const rows = await loadJsonl();
      setLoaded(true);
      return rows;
    },
    [] as DistilledRecord[],
    { shouldUpdate: jsonlDataChanged, intervalMs: 3000, fastPoll },
  );
  const curatedRecords = useIntervalPoll(
    async () => {
      const rows = await loadCuratedJsonl();
      setCuratedLoaded(true);
      return rows;
    },
    [] as DistilledRecord[],
    { shouldUpdate: jsonlDataChanged, intervalMs: 3000, fastPoll },
  );
  const [query, setQuery] = useState("");
  const [searchMode, setSearchMode] = useState<SearchMode>("keyword");
  const [mode, setMode] = useState<"all" | "thinking" | "nothinking">("all");
  const [category, setCategory] = useState(initialCategory);
  const [page, setPage] = useState(0);
  const [rankedHits, setRankedHits] = useState<SearchHit[]>([]);
  const [rankedTotal, setRankedTotal] = useState(0);
  const [rankedLoading, setRankedLoading] = useState(false);
  const [rankedUnavailable, setRankedUnavailable] = useState(false);

  const extractedIdSet = useMemo(
    () => new Set(curatedRecords.map((record) => recordId(record))),
    [curatedRecords],
  );
  const distilledVisible = useMemo(
    () => distilledRecords.filter((record) => !extractedIdSet.has(recordId(record))),
    [distilledRecords, extractedIdSet],
  );
  const records = dataset === "extracted" ? curatedRecords : distilledVisible;
  const isDistilledView = dataset === "distilled";
  const isSearchActive = query.trim().length > 0;
  const rankedSearchEnabled = isDistilledView && searchMode === "ranked";

  const setDatasetAndUrl = useCallback(
    (next: OutputDataset) => {
      setPage(0);
      if (next === "extracted" && searchMode === "ranked") {
        setSearchMode("keyword");
      }
      const params = new URLSearchParams(searchParams.toString());
      if (next === "distilled") {
        params.delete("dataset");
      } else {
        params.set("dataset", "extracted");
      }
      const qs = params.toString();
      router.replace(qs ? `/outputs?${qs}` : "/outputs");
    },
    [router, searchMode, searchParams],
  );

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
    if (!rankedSearchEnabled) return;
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
  }, [rankedSearchEnabled, query, mode, category, page]);

  useEffect(() => {
    if (!rankedSearchEnabled) return;
    const timer = setTimeout(() => {
      void runRankedSearch();
    }, 300);
    return () => clearTimeout(timer);
  }, [rankedSearchEnabled, runRankedSearch]);

  useEffect(() => {
    if (rankedUnavailable && rankedSearchEnabled) {
      setSearchMode("keyword");
    }
  }, [rankedUnavailable, rankedSearchEnabled]);

  const isRanked = isSearchActive && rankedSearchEnabled;
  const totalCount = isRanked ? rankedTotal : keywordFiltered.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / PAGE_SIZE));
  const keywordPageRows = keywordFiltered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const displayRows: { record: DistilledRecord; hit?: SearchHit }[] = isRanked
    ? rankedHits.map((hit) => ({ record: hit.record, hit }))
    : keywordPageRows.map((record) => ({ record }));
  const exportRecords = isSearchActive
    ? isRanked
      ? rankedHits.map((hit) => hit.record)
      : keywordFiltered
    : modeFiltered;
  const exportFilename =
    dataset === "extracted" ? "responses.high_quality.jsonl" : "responses.distilled.jsonl";
  const viewLoaded = dataset === "extracted" ? curatedLoaded : loaded;

  const onExport = () => {
    downloadJsonl(exportRecords, exportFilename);
  };

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
    if (distilledRecords.length === 0) return;
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
        <div className="page-toolbar">
          <h2>出力一覧</h2>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
            <nav
              role="tablist"
              aria-label="出力データセット"
              data-testid="outputs-dataset-tabs"
              style={{ display: "flex", gap: "0.25rem" }}
            >
              <button
                type="button"
                role="tab"
                aria-selected={dataset === "distilled"}
                className={`nav-link${dataset === "distilled" ? " nav-link-active" : ""}`}
                data-testid="outputs-dataset-distilled"
                onClick={() => setDatasetAndUrl("distilled")}
              >
                蒸留後
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={dataset === "extracted"}
                className={`nav-link${dataset === "extracted" ? " nav-link-active" : ""}`}
                data-testid="outputs-dataset-extracted"
                onClick={() => setDatasetAndUrl("extracted")}
              >
                抽出後
              </button>
            </nav>
            <button
              type="button"
              className="secondary-btn"
              data-testid="outputs-export-jsonl"
              disabled={!viewLoaded || exportRecords.length === 0}
              onClick={onExport}
            >
              JSONL出力
            </button>
            {isDistilledView ? (
              <button
                type="button"
                className="danger-btn"
                disabled={!loaded || distilledRecords.length === 0 || deletingAll}
                onClick={() => void onDeleteAll()}
              >
                {deletingAll ? "削除中…" : "全削除"}
              </button>
            ) : null}
          </div>
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
          disabled={!isSearchActive || !isDistilledView}
          title={
            !isSearchActive
              ? "検索クエリ入力時のみ利用可能"
              : !isDistilledView
                ? "BM25 検索は蒸留後ビューのみ利用可能"
                : undefined
          }
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

      {!viewLoaded ? (
        <p className="muted">
          {dataset === "extracted"
            ? "responses.high_quality.jsonl を読み込み中…"
            : "responses.jsonl を読み込み中…"}
          <br />
          (dashboard/public/ にシンボリックリンクまたはコピーを置いてください)
        </p>
      ) : isSearchActive ? (
        <p className="muted page-subtitle">
          {isRanked && rankedLoading ? "検索中… " : ""}
          {totalCount.toLocaleString()} / {records.length.toLocaleString()} 件 ヒット (ページ{" "}
          {page + 1} / {totalPages})
        </p>
      ) : (
        <p className="muted page-subtitle">
          全 {modeFiltered.length.toLocaleString()} 件 — フォルダを開いて閲覧
          {isDistilledView && curatedRecords.length > 0
            ? `（抽出済み ${curatedRecords.length.toLocaleString()} 件を除外）`
            : null}
        </p>
      )}

      {viewLoaded && !isSearchActive ? (
        <Suspense
          fallback={<p className="muted page-subtitle">フォルダ階層を読み込み中…</p>}
        >
          <OutputsHierarchyView
            records={modeFiltered}
            deletingId={deletingId}
            onDeleteRecord={(record) => void onDeleteOne(record)}
            allowDelete={isDistilledView}
          />
        </Suspense>
      ) : null}

      {viewLoaded && isSearchActive ? (
        <>
          <div className="outputs-table-wrap">
            <table className="data-table">
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
                  {isDistilledView ? <th>操作</th> : null}
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
                      <td>{r.category ?? ""}</td>
                      <td>{r.mode ?? ""}</td>
                      <td>{r.style_id ?? "-"}</td>
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
                      {isRanked ? (
                        <>
                          <td className="cell-nowrap">
                            {hit ? hit.score.toFixed(2) : "-"}
                          </td>
                          <td className="cell-truncate">
                            {hit?.snippet ? (
                              <pre className="snippet search-snippet">{hit.snippet}</pre>
                            ) : (
                              "-"
                            )}
                          </td>
                        </>
                      ) : null}
                      {isDistilledView ? (
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
                      ) : null}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="pagination">
            <button className="secondary-btn" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
              ‹ 前へ
            </button>
            <button
              className="secondary-btn"
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
