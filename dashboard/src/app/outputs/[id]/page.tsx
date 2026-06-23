"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { MarkdownView } from "@/components/MarkdownView";
import {
  DistilledRecord,
  findRecordById,
  formatRecordMarkdown,
  jsonlDataChanged,
  loadJsonl,
} from "@/lib/jsonl";
import { useIntervalPoll } from "@/lib/useIntervalPoll";

export default function OutputDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const records = useIntervalPoll(
    async () => loadJsonl(),
    [] as DistilledRecord[],
    { shouldUpdate: jsonlDataChanged },
  );

  const record = useMemo(() => findRecordById(records, id), [records, id]);
  const markdown = useMemo(
    () => (record ? formatRecordMarkdown(record) : ""),
    [record],
  );

  return (
    <>
      <Link href="/outputs" className="output-detail-back">
        ← 出力一覧に戻る
      </Link>

      {!record ? (
        <div className="output-detail">
          <p>レコードが見つかりません (id: {id})</p>
          <p style={{ color: "var(--muted)", fontSize: "0.9rem" }}>
            データがまだ読み込まれていないか、該当する出力が存在しません。
          </p>
        </div>
      ) : (
        <div className="output-detail">
          <MarkdownView source={markdown} />
        </div>
      )}
    </>
  );
}
