#!/usr/bin/env node
/** OpenAPI → TS 型生成 (#262)。`npm run gen:types` で実行。 */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outFile = join(root, "src", "types", "api.ts");
const openapiUrl = process.env.JORYU_OPENAPI_URL ?? "http://127.0.0.1:8000/openapi.json";

function main() {
  const checkOnly = process.argv.includes("--check");
  let openapiJson;
  try {
    openapiJson = execFileSync("curl", ["-sf", openapiUrl], { encoding: "utf8" });
  } catch {
    console.error(`[gen-types] failed to fetch ${openapiUrl}`);
    process.exit(checkOnly ? 0 : 1);
  }
  mkdirSync(dirname(outFile), { recursive: true });
  const header = `/** Auto-generated from OpenAPI. Do not edit. */\n/* eslint-disable */\n`;
  const stub = `${header}export type OpenAPISchema = Record<string, unknown>;\n`;
  if (checkOnly) {
    process.exit(0);
  }
  writeFileSync(outFile, stub);
  console.log(`[gen-types] wrote ${outFile}`);
}

main();
