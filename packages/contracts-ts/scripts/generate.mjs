// 从 schemas/*.schema.json（真值工件）生成 src/generated/*.ts。
// 用法：pnpm --filter @videoforge/contracts generate
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { compileFromFile } from "json-schema-to-typescript";

const here = path.dirname(fileURLToPath(import.meta.url));
const schemasDir = path.resolve(here, "../../../schemas");
const outDir = path.resolve(here, "../src/generated");

const banner = [
  "/* eslint-disable */",
  "/**",
  " * 由 scripts/generate.mjs 从 schemas/*.schema.json 生成，禁止手改。",
  " * 再生成：pnpm --filter @videoforge/contracts generate",
  " */",
].join("\n");

await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

const files = (await readdir(schemasDir)).filter((f) => f.endsWith(".schema.json")).sort();
if (files.length === 0) {
  throw new Error(`no *.schema.json under ${schemasDir}`);
}
for (const file of files) {
  const stem = file.replace(/\.schema\.json$/, "");
  const ts = await compileFromFile(path.join(schemasDir, file), {
    bannerComment: banner,
    cwd: schemasDir,
  });
  await writeFile(path.join(outDir, `${stem}.ts`), ts);
  console.log(`generated src/generated/${stem}.ts`);
}
