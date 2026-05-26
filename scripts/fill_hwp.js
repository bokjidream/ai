#!/usr/bin/env node
"use strict";

/**
 * fill_hwp.js <input.hwp> <output.hwp> '<field_mapping_json>'
 *
 * 표 셀 스캔 방식:
 *   1. 모든 표의 셀 텍스트를 읽어 라벨 셀 파악
 *   2. 라벨 셀 오른쪽(또는 아래) 빈 셀을 값 셀로 특정
 *   3. insertTextInCell로 값 삽입 (문서를 1회만 로드/저장)
 */

const path = require("node:path");
const fs = require("node:fs");

function loadKSkillRhwp() {
  const localPath = path.resolve(
    __dirname,
    "node_modules",
    "k-skill-rhwp",
    "src",
    "index.js"
  );
  if (fs.existsSync(localPath)) return require(localPath);

  const globalBase = process.env.APPDATA
    ? path.join(process.env.APPDATA, "npm", "node_modules")
    : null;
  if (globalBase) {
    const gp = path.join(globalBase, "k-skill-rhwp", "src", "index.js");
    if (fs.existsSync(gp)) return require(gp);
  }
  throw new Error(
    "k-skill-rhwp를 찾을 수 없습니다. 'cd ai/scripts && npm install' 후 재시도하세요."
  );
}

/** 공백을 모두 제거해 "성  명" → "성명" 처럼 정규화한다. */
function collapseSpaces(text) {
  return text.replace(/\s+/g, "");
}

function isValueCell(text) {
  if (text === "") return true;
  if (/^[\s_\-.]*$/.test(text)) return true;
  // "(핸드폰)(집전화)" 같은 괄호 힌트만 있는 셀도 값 셀로 허용
  const withoutParens = text
    .replace(/\([^)]*\)/g, "")
    .replace(/（[^）]*）/g, "")
    .trim();
  return withoutParens === "";
}

/** 모든 섹션·문단을 순회하며 표 셀 정보를 수집한다. */
function scanTableCells(doc) {
  const cells = [];
  const sectionCount = doc.getSectionCount();

  for (let s = 0; s < sectionCount; s++) {
    const paraCount = doc.getParagraphCount(s);
    for (let p = 0; p < paraCount; p++) {
      for (let c = 0; c < 32; c++) {
        let dims;
        try {
          dims = JSON.parse(doc.getTableDimensions(s, p, c));
        } catch (_) {
          break;
        }
        if (!dims || !dims.cellCount) break;

        for (let cellIdx = 0; cellIdx < dims.cellCount; cellIdx++) {
          try {
            const info = JSON.parse(doc.getCellInfo(s, p, c, cellIdx));
            const cpCount = doc.getCellParagraphCount(s, p, c, cellIdx);
            let fullText = "";
            for (let cp = 0; cp < cpCount; cp++) {
              const len = doc.getCellParagraphLength(s, p, c, cellIdx, cp);
              if (len > 0) {
                const chunk = doc.getTextInCell(s, p, c, cellIdx, cp, 0, len);
                fullText += (cp > 0 ? "\n" : "") + chunk;
              }
            }
            cells.push({
              s, p, c, cellIdx,
              row: info.row,
              col: info.col,
              rowSpan: info.rowSpan ?? 1,
              colSpan: info.colSpan ?? 1,
              text: fullText.trim(),
            });
          } catch (_) {
            // 개별 셀 오류는 skip
          }
        }
      }
    }
  }
  return cells;
}

/** 라벨 셀에 대응하는 값 셀을 찾는다. */
function findValueCell(cells, labelCell) {
  const { s, p, c, row, col, colSpan } = labelCell;

  // 전략 1: 같은 행, 바로 오른쪽 열
  const rightCol = col + colSpan;
  const right = cells.find(
    (cell) =>
      cell.s === s && cell.p === p && cell.c === c &&
      cell.row === row && cell.col === rightCol
  );
  if (right && isValueCell(right.text)) return right;

  // 전략 2: 바로 아래 행, 같은 열
  const below = cells.find(
    (cell) =>
      cell.s === s && cell.p === p && cell.c === c &&
      cell.row === row + labelCell.rowSpan && cell.col === col &&
      isValueCell(cell.text)
  );
  if (below) return below;

  return null;
}

async function main() {
  const [inputPath, outputPath, mappingFilePath] = process.argv.slice(2);

  if (!inputPath || !outputPath || !mappingFilePath) {
    process.stderr.write(
      "Usage: fill_hwp.js <input.hwp> <output.hwp> <mapping.json>\n"
    );
    process.exit(1);
  }

  const fieldMapping = JSON.parse(fs.readFileSync(mappingFilePath, "utf8"));
  const { loadDocument, writeHwp } = loadKSkillRhwp();
  const doc = await loadDocument(inputPath);

  try {
    // 1단계: 표 셀 전체 스캔
    const cells = scanTableCells(doc);

    const results = [];
    let fillCount = 0;

    // 2단계: 라벨 매칭 → 값 셀 찾기 → 삽입
    for (const [label, value] of Object.entries(fieldMapping)) {
      if (!value || String(value).trim() === "") continue;

      // 공백 정규화 후 라벨 포함 셀 탐색 ("성  명" → "성명" 처럼 매칭)
      const normalizedLabel = collapseSpaces(label);
      const labelCell = cells.find(
        (cell) => collapseSpaces(cell.text).includes(normalizedLabel)
      );
      if (!labelCell) {
        results.push({ label, matched: false });
        continue;
      }

      // 값 셀 찾기
      const valueCell = findValueCell(cells, labelCell);
      if (!valueCell) {
        results.push({ label, matched: true, filled: false, reason: "값 셀 없음" });
        continue;
      }

      try {
        const { s, p, c, cellIdx } = valueCell;
        const len = doc.getCellParagraphLength(s, p, c, cellIdx, 0);
        if (len > 0) {
          doc.deleteTextInCell(s, p, c, cellIdx, 0, 0, len);
        }
        doc.insertTextInCell(s, p, c, cellIdx, 0, 0, String(value));

        // 이후 탐색에서 중복 사용 방지
        valueCell.text = String(value);

        results.push({ label, matched: true, filled: true, value });
        fillCount++;
      } catch (e) {
        results.push({ label, matched: true, filled: false, reason: e.message });
      }
    }

    // 3단계: 저장
    writeHwp(doc, outputPath);

    process.stdout.write(
      JSON.stringify({ ok: true, count: fillCount, results })
    );
  } finally {
    doc.free();
  }
}

main().catch((e) => {
  process.stderr.write((e && e.stack ? e.stack : String(e)) + "\n");
  process.exit(1);
});
