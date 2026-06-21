"use client";

import { useEffect, useMemo, useState } from "react";

import { DistilledRecord, loadJsonl, searchRecords } from "@/lib/jsonl";

const PAGE_SIZE = 25;

export default function SearchPage() {
  const [records, setRecords] = useState<DistilledRecord[]>([]);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<"all" | "thinking" | "nothinking">("all");
  const [category, setCategory] = useState("");
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadJsonl().then((r) => {
      setRecords(r);
      setLoading(false);
    });
  }, []);

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

  return (
    <>
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

      {loading ? (
        <p style={{ color: "var(--muted)" }}>
          responses.jsonl を読み込み中…<br />
          (dashboard/public/responses.jsonl にシンボリックリンクまたはコピーを置いてください)
        </p>
      ) : (
        <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
          {filtered.length.toLocaleString()} / {records.length.toLocaleString()} 件 ヒット
          (ページ {page + 1} / {totalPages})
        </p>
      )}

      <table>
        <thead>
          <tr>
            <th>category</th>
            <th>mode</th>
            <th>prompt</th>
            <th>answer</th>
          </tr>
        </thead>
        <tbody>
          {pageRows.map((r, i) => (
            <tr key={`${page}-${i}`}>
              <td style={{ verticalAlign: "top" }}>{r.category ?? ""}</td>
              <td style={{ verticalAlign: "top" }}>{r.mode ?? ""}</td>
              <td>
                <pre className="snippet">{r.prompt}</pre>
              </td>
              <td>
                <pre className="snippet">{r.answer}</pre>
              </td>
            </tr>
          ))}
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
