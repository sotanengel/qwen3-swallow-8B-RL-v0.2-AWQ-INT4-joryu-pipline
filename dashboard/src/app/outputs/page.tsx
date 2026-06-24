"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { deleteAllOutputs, deleteOutput } from "@/lib/outputs";
import { useIntervalPoll } from "@/lib/useIntervalPoll";
import { useDistillJobFastPoll } from "@/lib/useDistillJobFastPoll";
import {
  DistilledRecord,
  jsonlDataChanged,
  loadJsonl,
  recordId,
  searchRecords,
  truncateText,
} from "@/lib/jsonl";

const PAGE_SIZE = 25;

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
  const [mode, setMode] = useState<"all" | "thinking" | "nothinking">("all");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(0);

  const categories = useMemo(() => {
    const set = new Set<string>();
    for (const r of records) {
      if (r.category) set.add(r.category);
    }
    return [...set].sort();
  }, [records]);

  const filtered = useMemo(
    () =>
      searchRecords(records, {
        query,
        mode,
        category: category || undefined,
      }),
    [records, query, mode, category],
  );

  const pageRows = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  const onDeleteOne = async (record: DistilledRecord) => {
    const id = recordId(record);
    if (typeof window !== "undefined" && !window.confirm("この出力を削除しますか？")) {
      return;
    }
    setDeletingId(id);
    setError(null);
    try {
      await deleteOutput(id);
      const nextFilteredLen = filtered.length - 1;
      const nextTotalPages = Math.max(1, Math.ceil(nextFilteredLen / PAGE_SIZE));
      if (page >= nextTotalPages) {
        setPage(Math.max(0, nextTotalPages - 1));
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
        >
          <option value="">category: all</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </section>

      {!loaded ? (
        <p style={{ color: "var(--muted)" }}>
          responses.jsonl を読み込み中…
          <br />
          (dashboard/public/responses.jsonl にシンボリックリンクまたはコピーを置いてください)
        </p>
      ) : (
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          {filtered.length.toLocaleString()} / {records.length.toLocaleString()} 件 ヒット (ページ{" "}
          {page + 1} / {totalPages})
        </p>
      )}

      <table>
        <thead>
          <tr>
            <th>category</th>
            <th>mode</th>
            <th>prompt</th>
            <th>created_at</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {pageRows.map((r) => {
            const id = recordId(r);
            return (
              <tr
                key={id}
                className="output-list-row"
                onClick={() => router.push(`/outputs/${id}`)}
              >
                <td style={{ verticalAlign: "top" }}>{r.category ?? ""}</td>
                <td style={{ verticalAlign: "top" }}>{r.mode ?? ""}</td>
                <td>{truncateText(r.prompt, 80)}</td>
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
  );
}
