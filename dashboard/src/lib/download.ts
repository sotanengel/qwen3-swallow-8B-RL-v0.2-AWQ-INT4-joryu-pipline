import type { DistilledRecord } from "./jsonl";
import { recordsToJsonl } from "./jsonl";

/** レコードを JSONL ファイルとしてブラウザにダウンロードする。 */
export function downloadJsonl(records: DistilledRecord[], filename: string): void {
  const text = recordsToJsonl(records);
  const blob = new Blob([text], { type: "application/x-ndjson" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
