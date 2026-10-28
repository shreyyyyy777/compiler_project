#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const sharp = require("sharp");

const input = path.resolve(process.argv[2] || "benchmarks/review_2026_10_27/v1_v2_comparison.json");
const outputDir = path.resolve(process.argv[3] || "benchmarks/review_2026_10_27/graphs");
const payload = JSON.parse(fs.readFileSync(input, "utf8"));
fs.mkdirSync(outputDir, { recursive: true });

const colors = { V1: "#2563EB", V2: "#F59E0B", ink: "#10233B", grid: "#DCE3EC", muted: "#5B6B80" };
const escapeXml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;" }[char]));
const row = (workload, version) => payload.summary.find((item) => item.workload === workload && item.version === version);
const workloads = [...new Set(payload.summary.map((item) => item.workload))];

function svgShell(title, subtitle, body, note = "") {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" viewBox="0 0 1600 900">
  <rect width="1600" height="900" fill="#FFFFFF"/>
  <text x="100" y="82" font-family="Arial, Helvetica, sans-serif" font-size="42" font-weight="700" fill="${colors.ink}">${escapeXml(title)}</text>
  <text x="100" y="122" font-family="Arial, Helvetica, sans-serif" font-size="21" fill="${colors.muted}">${escapeXml(subtitle)}</text>
  ${body}
  ${note ? `<text x="100" y="862" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="${colors.muted}">${escapeXml(note)}</text>` : ""}
</svg>`;
}

function groupedBars({ title, subtitle, yLabel, values, formatter, filename, note, maxValue }) {
  const left = 170, top = 185, width = 1320, height = 560;
  const yMax = maxValue || Math.max(...values.flatMap((item) => [item.V1, item.V2])) * 1.18;
  const gridCount = 5;
  let body = `<text transform="translate(44 ${top + height / 2}) rotate(-90)" font-family="Arial, Helvetica, sans-serif" font-size="22" fill="${colors.ink}" text-anchor="middle">${escapeXml(yLabel)}</text>`;
  for (let index = 0; index <= gridCount; index++) {
    const value = (yMax * index) / gridCount;
    const y = top + height - (value / yMax) * height;
    body += `<line x1="${left}" y1="${y}" x2="${left + width}" y2="${y}" stroke="${colors.grid}" stroke-width="1"/>`;
    body += `<text x="${left - 18}" y="${y + 7}" font-family="Arial, Helvetica, sans-serif" font-size="18" fill="${colors.muted}" text-anchor="end">${escapeXml(formatter(value, true))}</text>`;
  }
  const groupWidth = width / values.length;
  const barWidth = 118;
  values.forEach((item, index) => {
    const center = left + groupWidth * index + groupWidth / 2;
    ["V1", "V2"].forEach((version, versionIndex) => {
      const value = item[version];
      const barHeight = (value / yMax) * height;
      const x = center + (versionIndex === 0 ? -barWidth - 8 : 8);
      const y = top + height - barHeight;
      body += `<rect x="${x}" y="${y}" width="${barWidth}" height="${barHeight}" rx="8" fill="${colors[version]}"/>`;
      body += `<text x="${x + barWidth / 2}" y="${Math.max(top + 20, y - 14)}" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="700" fill="${colors.ink}" text-anchor="middle">${escapeXml(formatter(value, false))}</text>`;
    });
    body += `<text x="${center}" y="${top + height + 42}" font-family="Arial, Helvetica, sans-serif" font-size="20" fill="${colors.ink}" text-anchor="middle">${escapeXml(item.label)}</text>`;
  });
  body += `<rect x="1120" y="140" width="24" height="24" rx="4" fill="${colors.V1}"/><text x="1156" y="160" font-family="Arial, Helvetica, sans-serif" font-size="20" fill="${colors.ink}">V1 09de2a6</text>`;
  body += `<rect x="1320" y="140" width="24" height="24" rx="4" fill="${colors.V2}"/><text x="1356" y="160" font-family="Arial, Helvetica, sans-serif" font-size="20" fill="${colors.ink}">V2 d09673e</text>`;
  const svg = svgShell(title, subtitle, body, note);
  const svgPath = path.join(outputDir, `${filename}.svg`);
  const pngPath = path.join(outputDir, `${filename}.png`);
  fs.writeFileSync(svgPath, svg);
  return sharp(Buffer.from(svg)).png().toFile(pngPath);
}

const labels = {
  "suffix-language": "Suffix language",
  "wildcard-scan": "Wildcard scan",
  "alternation-loop": "Alternation loop",
};

await groupedBars({
  title: "V1 and V2 matching runtime on shared syntax",
  subtitle: "Warm lazy DFA, 200 measured samples per version and workload, lower is better",
  yLabel: "Median matching time (ms)",
  values: workloads.map((name) => ({ label: labels[name], V1: row(name, "V1").match_median_ns / 1e6, V2: row(name, "V2").match_median_ns / 1e6 })),
  formatter: (value, axis) => axis ? value.toFixed(1) : value.toFixed(3),
  filename: "matching_runtime_median",
  note: "Same Python 3.14.5 interpreter and machine. Workloads exclude V2-only syntax.",
  maxValue: 2.1,
});

await groupedBars({
  title: "Process peak memory stayed effectively flat",
  subtitle: "Median maximum resident set size from isolated worker processes",
  yLabel: "Peak RSS (MiB)",
  values: workloads.map((name) => ({ label: labels[name], V1: row(name, "V1").process_max_rss_bytes_median / 1048576, V2: row(name, "V2").process_max_rss_bytes_median / 1048576 })),
  formatter: (value, axis) => axis ? value.toFixed(0) : value.toFixed(2),
  filename: "memory_peak_rss",
  note: "Zero-based axis. RSS includes interpreter and imported modules, so use it as a coarse process-level check.",
  maxValue: 32,
});

await groupedBars({
  title: "Lazy DFA state counts matched across versions",
  subtitle: "States materialized after warmup for the exact input in each workload",
  yLabel: "Lazy DFA states explored",
  values: workloads.map((name) => ({ label: labels[name], V1: row(name, "V1").lazy_dfa_states_explored, V2: row(name, "V2").lazy_dfa_states_explored })),
  formatter: (value, axis) => axis ? value.toFixed(0) : String(Math.round(value)),
  filename: "lazy_dfa_states",
  note: "Equal state counts do not imply equal runtime; V2 performs generalized character-class signature checks per step.",
  maxValue: 8,
});

console.log(JSON.stringify({ input, outputDir, files: fs.readdirSync(outputDir).sort() }));
