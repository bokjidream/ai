#!/usr/bin/env node
"use strict";

/**
 * fill_hwp.js <input.hwp> <output.hwp> '<field_mapping_json>'
 *
 * field_mapping: {"필드라벨": "값", ...}
 * replaceAll로 각 라벨을 값으로 순차 치환.
 * 결과를 JSON으로 stdout 출력.
 *
 * 한계: replaceAll은 본문 문단만 스캔 (표 셀 제외).
 */

const path = require("node:path");
const fs = require("node:fs");

function loadKSkillRhwp() {
  // 1) scripts/node_modules (로컬 설치)
  const localPath = path.resolve(
    __dirname,
    "node_modules",
    "k-skill-rhwp",
    "src",
    "index.js"
  );
  if (fs.existsSync(localPath)) return require(localPath);

  // 2) 전역 npm (Windows: %APPDATA%\npm\node_modules)
  const globalBase =
    process.env.APPDATA
      ? path.join(process.env.APPDATA, "npm", "node_modules")
      : null;
  if (globalBase) {
    const globalPath = path.join(globalBase, "k-skill-rhwp", "src", "index.js");
    if (fs.existsSync(globalPath)) return require(globalPath);
  }

  throw new Error(
    "k-skill-rhwp를 찾을 수 없습니다. " +
      "'cd ai/scripts && npm install' 또는 'npm install -g k-skill-rhwp' 후 재시도하세요."
  );
}

async function main() {
  const [inputPath, outputPath, mappingJson] = process.argv.slice(2);

  if (!inputPath || !outputPath || !mappingJson) {
    process.stderr.write(
      "Usage: fill_hwp.js <input.hwp> <output.hwp> '<mapping_json>'\n"
    );
    process.exit(1);
  }

  const fieldMapping = JSON.parse(mappingJson);
  const { replaceAll } = loadKSkillRhwp();

  const entries = Object.entries(fieldMapping).filter(
    ([, value]) => String(value).trim() !== ""
  );

  if (entries.length === 0) {
    fs.copyFileSync(inputPath, outputPath);
    process.stdout.write(
      JSON.stringify({ ok: true, count: 0, replacements: [] })
    );
    return;
  }

  let currentInput = inputPath;
  const tmpFiles = [];
  const results = [];

  for (let i = 0; i < entries.length; i++) {
    const [label, value] = entries[i];
    const isLast = i === entries.length - 1;
    const currentOutput = isLast ? outputPath : `${outputPath}.tmp${i}`;

    try {
      const result = await replaceAll({
        input: currentInput,
        output: currentOutput,
        query: label,
        replacement: String(value),
        caseSensitive: false,
      });
      results.push({ label, value, count: result.count ?? 0 });
    } catch (err) {
      // 치환 실패 시 해당 단계 skip — 이전 파일을 그대로 복사
      fs.copyFileSync(currentInput, currentOutput);
      results.push({ label, value, count: 0, error: err.message });
    }

    if (i > 0 && currentInput !== inputPath) {
      tmpFiles.push(currentInput);
    }
    currentInput = currentOutput;
  }

  for (const tmp of tmpFiles) {
    try {
      fs.unlinkSync(tmp);
    } catch (_) {}
  }

  const totalCount = results.reduce((s, r) => s + r.count, 0);
  process.stdout.write(
    JSON.stringify({ ok: true, count: totalCount, replacements: results })
  );
}

main().catch((err) => {
  process.stderr.write(err.message + "\n");
  process.exit(1);
});
