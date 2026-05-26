#!/usr/bin/env node
"use strict";

/**
 * 사용법:
 *   fill_hwp.js <input> <output> <mapping.json>   -- 표 셀 채우기 (원본 포맷 보존)
 *   fill_hwp.js --scan <input>                    -- 라벨 후보 셀 목록 출력
 */

const path = require("node:path");
const fs = require("node:fs");
const AdmZip = require("adm-zip");

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
  if (/^[\s_\-.□○]+$/.test(text)) return true;
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

/**
 * 라벨 후보 셀만 추출한다.
 * - 짧고(collapsed 기준 1~20자) 단일 행인 셀
 * - 체크박스·번호·기호만 있는 셀은 제외
 */
function extractLabelCandidates(cells) {
  const seen = new Set();
  const labels = [];
  for (const cell of cells) {
    const t = cell.text;
    if (!t || t.includes("\n")) continue;
    const collapsed = collapseSpaces(t);
    if (collapsed.length < 1 || collapsed.length > 20) continue;
    // 체크박스·기호·번호만 있는 셀 제외
    if (/^[□○◎※①②③④⑤⑥⑦⑧⑨⑩●\s\-_.()\d]+$/.test(collapsed)) continue;
    if (seen.has(collapsed)) continue;
    seen.add(collapsed);
    labels.push(t.trim());
  }
  return labels;
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

// ─── HWPX 직접 XML 패치 ───────────────────────────────────────────────────────

function escapeXml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

/**
 * XML에서 openStart 위치의 <tag ...> 에 대응하는 </tag> 직후 인덱스를 반환한다.
 * 중첩된 동일 태그를 올바르게 처리한다.
 */
function findMatchingClose(xml, openStart, tag) {
  let depth = 0;
  let i = openStart;
  while (i < xml.length) {
    if (xml.startsWith(`<${tag} `, i) || xml.startsWith(`<${tag}>`, i)) {
      depth++;
      i += tag.length + 2;
    } else if (xml.startsWith(`</${tag}>`, i)) {
      depth--;
      if (depth === 0) return i + tag.length + 3;
      i += tag.length + 3;
    } else {
      i++;
    }
  }
  return xml.length;
}

/**
 * section0.xml 에서 fill 정보에 해당하는 값 셀의 텍스트를 교체한다.
 *
 * 셀 패턴 3가지:
 *   A. 빈 셀  — <hp:run .../>  →  <hp:run ...><hp:t>값</hp:t></hp:run>
 *   B. 단일 힌트 셀  — <hp:t>힌트</hp:t>  →  <hp:t>값</hp:t>
 *   C. 다중 단락 힌트 셀  — 첫 <hp:t> → 값, 나머지 → <hp:t/>
 */
function patchCellInXml(xml, fill) {
  const { labelText, valueCellCol, valueCellRow, value } = fill;
  const escaped = escapeXml(value);

  // 1. 라벨 텍스트로 테이블 위치 찾기
  const labelTag = `<hp:t>${labelText}</hp:t>`;
  const labelIdx = xml.indexOf(labelTag);
  if (labelIdx === -1) return xml;

  const tblStart = xml.lastIndexOf("<hp:tbl ", labelIdx);
  if (tblStart === -1) return xml;
  const tblEnd = findMatchingClose(xml, tblStart, "hp:tbl");

  // 2. 테이블 내에서 값 셀 cellAddr 찾기
  const cellAddrStr = `<hp:cellAddr colAddr="${valueCellCol}" rowAddr="${valueCellRow}"/>`;
  const addrIdx = xml.indexOf(cellAddrStr, tblStart);
  if (addrIdx === -1 || addrIdx >= tblEnd) return xml;

  // 3. 값 셀 subList 범위 찾기 (cellAddr 앞의 </hp:subList> 역탐색)
  const subListEndTag = "</hp:subList>";
  const subListEndIdx = xml.lastIndexOf(subListEndTag, addrIdx);
  if (subListEndIdx === -1) return xml;
  const subListStartIdx = xml.lastIndexOf("<hp:subList", subListEndIdx);
  if (subListStartIdx === -1) return xml;

  const sliceEnd = subListEndIdx + subListEndTag.length;
  const subListSlice = xml.slice(subListStartIdx, sliceEnd);

  // 4. 패턴 판별 및 교체
  const hasHpT = /<hp:t>/.test(subListSlice);
  let patched;

  if (!hasHpT) {
    // 케이스 A: 빈 셀 — 첫 번째 self-closing run 을 텍스트 run 으로 변환
    patched = subListSlice.replace(
      /<hp:run([^>]*)\/>/,
      (_, attrs) => `<hp:run${attrs}><hp:t>${escaped}</hp:t></hp:run>`
    );
    if (patched === subListSlice) return xml;
  } else {
    // 케이스 B/C: 힌트 텍스트 교체
    let firstReplaced = false;
    patched = subListSlice.replace(/<hp:t>[^<]*<\/hp:t>/g, () => {
      if (!firstReplaced) {
        firstReplaced = true;
        return `<hp:t>${escaped}</hp:t>`;
      }
      return "<hp:t/>";
    });
    if (!firstReplaced) return xml;
  }

  return xml.slice(0, subListStartIdx) + patched + xml.slice(sliceEnd);
}

/**
 * HWPX를 exportHwpx() 없이 저장한다.
 * 원본 ZIP의 Contents/section0.xml 만 패치하고 나머지는 그대로 복사한다.
 */
function writeHwpxPatched(inputPath, outputPath, fills) {
  const originalZip = new AdmZip(inputPath);
  let sectionXml = originalZip.readAsText("Contents/section0.xml");

  for (const fill of fills) {
    sectionXml = patchCellInXml(sectionXml, fill);
  }

  const newZip = new AdmZip();
  for (const entry of originalZip.getEntries()) {
    if (entry.isDirectory) continue;
    if (entry.entryName === "Contents/section0.xml") {
      newZip.addFile(entry.entryName, Buffer.from(sectionXml, "utf8"));
    } else {
      newZip.addFile(entry.entryName, entry.getData());
    }
  }
  newZip.writeZip(outputPath);
}

// ─────────────────────────────────────────────────────────────────────────────

async function scanMode(inputPath) {
  const { loadDocument } = loadKSkillRhwp();
  const doc = await loadDocument(inputPath);
  try {
    const cells = scanTableCells(doc);
    const labels = extractLabelCandidates(cells);
    process.stdout.write(JSON.stringify({ ok: true, labels }));
  } finally {
    doc.free();
  }
}

async function fillMode(inputPath, outputPath, mappingFilePath) {
  const fieldMapping = JSON.parse(fs.readFileSync(mappingFilePath, "utf8"));
  const { loadDocument } = loadKSkillRhwp();
  const doc = await loadDocument(inputPath);

  try {
    const cells = scanTableCells(doc);
    const format = doc.getSourceFormat(); // "hwp" | "hwpx"
    const results = [];
    const fills = []; // HWPX 전용: XML 패치에 필요한 정보

    for (const [label, value] of Object.entries(fieldMapping)) {
      if (!value || String(value).trim() === "") continue;

      const normalizedLabel = collapseSpaces(label);
      const labelCell = cells.find(
        (cell) => collapseSpaces(cell.text).includes(normalizedLabel)
      );
      if (!labelCell) {
        results.push({ label, matched: false });
        continue;
      }

      const valueCell = findValueCell(cells, labelCell);
      if (!valueCell) {
        results.push({ label, matched: true, filled: false, reason: "값 셀 없음" });
        continue;
      }

      if (format === "hwpx") {
        // HWPX: XML 직접 패치 — WASM insertTextInCell 사용 안 함
        fills.push({
          labelText: labelCell.text,
          valueCellCol: valueCell.col,
          valueCellRow: valueCell.row,
          value: String(value),
        });
        results.push({ label, matched: true, filled: true, value });
      } else {
        // HWP: 기존 WASM API 사용
        try {
          const { s, p, c, cellIdx } = valueCell;
          const len = doc.getCellParagraphLength(s, p, c, cellIdx, 0);
          if (len > 0) doc.deleteTextInCell(s, p, c, cellIdx, 0, 0, len);
          doc.insertTextInCell(s, p, c, cellIdx, 0, 0, String(value));
          valueCell.text = String(value);
          results.push({ label, matched: true, filled: true, value });
        } catch (e) {
          results.push({ label, matched: true, filled: false, reason: e.message });
        }
      }
    }

    if (format === "hwpx") {
      writeHwpxPatched(inputPath, outputPath, fills);
    } else {
      fs.writeFileSync(outputPath, Buffer.from(doc.exportHwp()));
    }

    const fillCount = results.filter((r) => r.filled).length;
    process.stdout.write(JSON.stringify({ ok: true, count: fillCount, results }));
  } finally {
    doc.free();
  }
}

async function main() {
  const args = process.argv.slice(2);

  if (args[0] === "--scan") {
    const inputPath = args[1];
    if (!inputPath) {
      process.stderr.write("Usage: fill_hwp.js --scan <input.hwp>\n");
      process.exit(1);
    }
    return scanMode(inputPath);
  }

  const [inputPath, outputPath, mappingFilePath] = args;
  if (!inputPath || !outputPath || !mappingFilePath) {
    process.stderr.write(
      "Usage:\n" +
      "  fill_hwp.js <input> <output> <mapping.json>\n" +
      "  fill_hwp.js --scan <input>\n"
    );
    process.exit(1);
  }
  return fillMode(inputPath, outputPath, mappingFilePath);
}

main().catch((e) => {
  process.stderr.write((e && e.stack ? e.stack : String(e)) + "\n");
  process.exit(1);
});
