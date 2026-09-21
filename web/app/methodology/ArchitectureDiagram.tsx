"use client";

import styles from "./methodology.module.css";

/** Static architecture diagram, hand-drawn in SVG (no charting/diagramming
 * library) — mirrors PLAN.md's mermaid flowchart: all heavy compute runs
 * offline on the author's machine; Cloudflare's free plan only serves
 * static assets plus one thin Worker endpoint; the browser does the rest
 * (canvas rendering, nearest-neighbor search, DuckDB-WASM).
 */
export default function ArchitectureDiagram() {
  const boxW = 168;
  const boxH = 34;
  const gapY = 14;

  const col1 = [
    "nba_api fetch\n(throttled, cached)",
    "Raw cache\n(data/raw)",
    "Canonical tables\n(Parquet)",
    "Feature pipelines\n+ model training",
    "Exports\n(JSON, grids, Parquet)",
    "make deploy\n(wrangler)",
  ];
  const col2 = ["Worker static assets\n(Next.js export + data)", "Worker /api/ask", "Workers AI", "Cache API + KV counter"];
  const col3 = ["Visitor browser\n(canvas, kNN, DuckDB-WASM)"];

  const col1X = 20;
  const col2X = col1X + boxW + 70;
  const col3X = col2X + boxW + 70;
  const startY = 34;

  const height = startY + Math.max(col1.length, col2.length + 1) * (boxH + gapY) + 20;
  const width = col3X + boxW + 20;

  const yFor = (i: number) => startY + i * (boxH + gapY);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={styles.diagramSvg}>
      <defs>
        <marker id="arrowhead" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 Z" className={styles.diagramBox} />
        </marker>
      </defs>

      <text x={col1X} y={16} className={styles.diagramGroupLabel}>
        Home machine
      </text>
      <text x={col2X} y={16} className={styles.diagramGroupLabel}>
        Cloudflare free plan
      </text>
      <text x={col3X} y={16} className={styles.diagramGroupLabel}>
        Browser
      </text>

      {col1.map((label, i) => (
        <g key={label}>
          <rect x={col1X} y={yFor(i)} width={boxW} height={boxH} rx={0} className={styles.diagramBox} />
          {label.split("\n").map((line, li) => (
            <text
              key={li}
              x={col1X + boxW / 2}
              y={yFor(i) + boxH / 2 + (li === 0 && label.includes("\n") ? -4 : 10)}
              textAnchor="middle"
              className={styles.diagramBoxLabel}
            >
              {line}
            </text>
          ))}
          {i > 0 && (
            <line
              x1={col1X + boxW / 2}
              y1={yFor(i - 1) + boxH}
              x2={col1X + boxW / 2}
              y2={yFor(i)}
              className={styles.diagramArrow}
            />
          )}
        </g>
      ))}

      {/* col1 -> col2: deploy feeds static assets */}
      <line
        x1={col1X + boxW}
        y1={yFor(col1.length - 1) + boxH / 2}
        x2={col2X}
        y2={yFor(0) + boxH / 2}
        className={styles.diagramArrow}
      />

      {col2.map((label, i) => (
        <g key={label}>
          <rect x={col2X} y={yFor(i)} width={boxW} height={boxH} rx={0} className={styles.diagramBox} />
          {label.split("\n").map((line, li) => (
            <text
              key={li}
              x={col2X + boxW / 2}
              y={yFor(i) + boxH / 2 + (li === 0 && label.includes("\n") ? -4 : 10)}
              textAnchor="middle"
              className={styles.diagramBoxLabel}
            >
              {line}
            </text>
          ))}
        </g>
      ))}
      {/* /api/ask -> Workers AI, /api/ask -> Cache+KV */}
      <line
        x1={col2X + boxW / 2}
        y1={yFor(1) + boxH}
        x2={col2X + boxW / 2}
        y2={yFor(2)}
        className={styles.diagramArrow}
      />
      <line
        x1={col2X + boxW / 2}
        y1={yFor(2) + boxH}
        x2={col2X + boxW / 2}
        y2={yFor(3)}
        className={styles.diagramArrow}
      />

      {/* col2 static assets -> col3 browser */}
      <line
        x1={col2X + boxW}
        y1={yFor(0) + boxH / 2}
        x2={col3X}
        y2={yFor(0) + boxH / 2}
        className={styles.diagramArrow}
      />
      <rect x={col3X} y={yFor(0)} width={boxW} height={boxH} rx={0} className={styles.diagramBox} />
      {col3[0].split("\n").map((line, li) => (
        <text
          key={li}
          x={col3X + boxW / 2}
          y={yFor(0) + boxH / 2 + (li === 0 ? -4 : 10)}
          textAnchor="middle"
          className={styles.diagramBoxLabel}
        >
          {line}
        </text>
      ))}

      {/* browser -> /api/ask (question round trip), drawn as a curve below */}
      <path
        d={`M ${col3X} ${yFor(0) + boxH + 20} C ${col2X + boxW + 40} ${yFor(0) + boxH + 40}, ${col2X + boxW + 10} ${yFor(1) + boxH / 2 + 20}, ${col2X + boxW} ${yFor(1) + boxH / 2}`}
        className={styles.diagramArrow}
        strokeDasharray="3 3"
      />
    </svg>
  );
}
