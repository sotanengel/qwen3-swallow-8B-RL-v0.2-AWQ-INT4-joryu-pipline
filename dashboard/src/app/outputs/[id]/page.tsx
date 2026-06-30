"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";

import { MarkdownView } from "@/components/MarkdownView";
import { ToolEventTimeline } from "@/components/ToolEventTimeline";
import {
  DistilledRecord,
  findRecordById,
  formatRecordMarkdown,
  jsonlDataChanged,
  loadJsonl,
  recordLooksTruncated,
} from "@/lib/jsonl";
import { extractToolEvents } from "@/lib/tool-events";
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
  const toolEvents = useMemo(
    () => (record ? extractToolEvents(record) : []),
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
          <p className="muted page-subtitle">
            データがまだ読み込まれていないか、該当する出力が存在しません。
          </p>
        </div>
      ) : (
        <div className="output-detail">
          {recordLooksTruncated(record) ? (
            <p className="truncation-warning" role="status">
              この出力は生成上限で途中切断された可能性があります（finish_reason=
              {record.finish_reason ?? "不明"}）
            </p>
          ) : null}
          <ToolEventTimeline events={toolEvents} />
          <MarkdownView source={markdown} />
        </div>
      )}
    </>
  );
}
