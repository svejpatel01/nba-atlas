"use client";

import { useEffect, useMemo, useState } from "react";
import {
  ACTION_FAMILY_LABELS,
  loadGrid,
  loadLeagueHex,
  loadPlayerHex,
  loadPlayerMetrics,
  loadQuadrant,
  lookupGridXfg,
  ZONE_LABELS,
  type GridMeta,
  type HexAggregate,
  type PlayerMetrics,
  type QuadrantPoint,
} from "../../lib/shot-quality";
import CourtCanvas from "./CourtCanvas";
import styles from "./shot-quality.module.css";

const SEASONS = [
  "2015-16",
  "2016-17",
  "2017-18",
  "2018-19",
  "2019-20",
  "2020-21",
  "2021-22",
  "2022-23",
  "2023-24",
  "2024-25",
  "2025-26",
];
const ACTION_FAMILIES = Object.keys(ACTION_FAMILY_LABELS);

export default function ShotQualityPage() {
  const [season, setSeason] = useState("2023-24");
  const [search, setSearch] = useState("");
  const [selectedPlayer, setSelectedPlayer] = useState<{ id: number; name: string } | null>(null);
  const [colorMode, setColorMode] = useState<"diff" | "xfg">("diff");
  const [actionFamily, setActionFamily] = useState("catch_and_shoot");

  const [quadrant, setQuadrant] = useState<QuadrantPoint[]>([]);
  const [metrics, setMetrics] = useState<PlayerMetrics[]>([]);
  const [hexes, setHexes] = useState<HexAggregate[]>([]);
  const [grid, setGrid] = useState<{ bytes: Uint8Array; meta: GridMeta } | null>(null);
  const [clickedPoint, setClickedPoint] = useState<{ x: number; y: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadGrid()
      .then(setGrid)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load grid."));
  }, []);

  useEffect(() => {
    Promise.all([loadQuadrant(season), loadPlayerMetrics(season)])
      .then(([q, m]) => {
        setQuadrant(q);
        setMetrics(m);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load season data."));
  }, [season]);

  function handleSeasonChange(next: string) {
    setSeason(next);
    setClickedPoint(null);
  }

  useEffect(() => {
    if (!selectedPlayer) {
      loadLeagueHex(season).then(setHexes).catch(() => setHexes([]));
      return;
    }
    loadPlayerHex(season, selectedPlayer.id)
      .then(setHexes)
      .catch(() => setHexes([]));
  }, [season, selectedPlayer]);

  const searchResults = useMemo(() => {
    if (search.trim().length < 2) return [];
    const q = search.toLowerCase();
    return metrics.filter((m) => m.player_name.toLowerCase().includes(q)).slice(0, 8);
  }, [metrics, search]);

  const selectedMetrics = selectedPlayer
    ? metrics.find((m) => m.player_id === selectedPlayer.id)
    : null;

  const clickedXfg =
    grid && clickedPoint
      ? lookupGridXfg(grid.bytes, grid.meta, clickedPoint.x, clickedPoint.y, actionFamily)
      : null;

  return (
    <main className={styles.page}>
      <div className={styles.header}>
        <h1>Shot quality court</h1>
        <p>
          Every shot is scored against an expected field-goal probability (xFG) — what an
          average NBA player would shoot from that spot, in that situation. Color shows whether
          a player made more or fewer shots than expected for the locations they shot from.
        </p>
      </div>

      <div className={styles.controlBar}>
        <select
          value={season}
          onChange={(e) => handleSeasonChange(e.target.value)}
          className={styles.select}
        >
          {SEASONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <div className={styles.searchBox}>
          <input
            type="text"
            placeholder="Search a player…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={styles.searchInput}
          />
          {searchResults.length > 0 && (
            <ul className={styles.searchResults}>
              {searchResults.map((m) => (
                <li key={m.player_id}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedPlayer({ id: m.player_id, name: m.player_name });
                      setSearch("");
                    }}
                  >
                    {m.player_name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {selectedPlayer && (
          <button type="button" className={styles.clearButton} onClick={() => setSelectedPlayer(null)}>
            Clear ({selectedPlayer.name}) — showing league average
          </button>
        )}

        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={colorMode === "xfg"}
            onChange={(e) => setColorMode(e.target.checked ? "xfg" : "diff")}
          />
          Color by xFG% instead of FG% − xFG%
        </label>
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.body}>
        <div className={styles.courtArea}>
          <CourtCanvas
            hexes={hexes}
            colorMode={colorMode}
            onCourtClick={(x, y) => setClickedPoint({ x, y })}
            clickedPoint={clickedPoint}
          />
          <div className={styles.courtCaption}>
            Hexagons are sized by shot frequency.{" "}
            {colorMode === "diff"
              ? "Blue = made more than expected here, red = fewer."
              : "Darker = higher expected make probability."}{" "}
            Click anywhere to see the modeled xFG% for a chosen shot type below.
          </div>
        </div>

        <aside className={styles.sidePanel}>
          <h3>Click-anywhere xFG lookup</h3>
          <select
            value={actionFamily}
            onChange={(e) => setActionFamily(e.target.value)}
            className={styles.select}
          >
            {ACTION_FAMILIES.map((f) => (
              <option key={f} value={f}>
                {ACTION_FAMILY_LABELS[f]}
              </option>
            ))}
          </select>
          <p className={styles.gridResult}>
            {clickedPoint
              ? clickedXfg !== null
                ? `${(clickedXfg * 100).toFixed(0)}% expected, for a ${ACTION_FAMILY_LABELS[actionFamily].toLowerCase()} from here`
                : "Outside the modeled area."
              : "Click the court to see a prediction."}
          </p>

          {selectedPlayer && selectedMetrics && (
            <>
              <h3>{selectedPlayer.name}</h3>
              <dl className={styles.statList}>
                <dt>Attempts</dt>
                <dd>{selectedMetrics.attempts}</dd>
                <dt>FG%</dt>
                <dd>{(selectedMetrics.fg_pct * 100).toFixed(1)}%</dd>
                <dt>Avg xFG%</dt>
                <dd>{(selectedMetrics.avg_xfg * 100).toFixed(1)}%</dd>
                <dt>Shot selection</dt>
                <dd>{selectedMetrics.shot_selection >= 0 ? "+" : ""}{(selectedMetrics.shot_selection * 100).toFixed(1)}pp</dd>
                <dt>Shot making</dt>
                <dd>{selectedMetrics.shot_making >= 0 ? "+" : ""}{selectedMetrics.shot_making.toFixed(3)} pts/shot</dd>
              </dl>

              <h3>By zone</h3>
              <table className={styles.zoneTable}>
                <thead>
                  <tr>
                    <th>Zone</th>
                    <th>Att.</th>
                    <th>FG%</th>
                    <th>xFG%</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(ZONE_LABELS).map(([zone, label]) => {
                    const attempts = selectedMetrics[`${zone}_attempts`] as number | undefined;
                    if (!attempts) return null;
                    const fgPct = selectedMetrics[`${zone}_fg_pct`] as number;
                    const xfgPct = selectedMetrics[`${zone}_xfg_pct`] as number;
                    return (
                      <tr key={zone}>
                        <td>{label}</td>
                        <td>{attempts}</td>
                        <td>{(fgPct * 100).toFixed(1)}%</td>
                        <td>{(xfgPct * 100).toFixed(1)}%</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </aside>
      </div>

      <QuadrantScatter
        points={quadrant}
        selectedPlayerId={selectedPlayer?.id ?? null}
        onSelect={(p) => setSelectedPlayer({ id: p.player_id, name: p.player_name })}
      />
    </main>
  );
}

function QuadrantScatter({
  points,
  selectedPlayerId,
  onSelect,
}: {
  points: QuadrantPoint[];
  selectedPlayerId: number | null;
  onSelect: (p: QuadrantPoint) => void;
}) {
  const width = 640;
  const height = 400;
  const padding = 40;
  const xs = points.map((p) => p.shot_selection);
  const ys = points.map((p) => p.shot_making);
  const xMin = Math.min(0, ...xs);
  const xMax = Math.max(0, ...xs);
  const yMin = Math.min(0, ...ys);
  const yMax = Math.max(0, ...ys);
  const toPx = (x: number, y: number): [number, number] => [
    padding + ((x - xMin) / (xMax - xMin || 1)) * (width - 2 * padding),
    height - padding - ((y - yMin) / (yMax - yMin || 1)) * (height - 2 * padding),
  ];

  return (
    <div className={styles.quadrantSection}>
      <h3>Shot selection vs. shot making</h3>
      <p className={styles.sectionHint}>
        Right = takes better shots than average. Up = makes shots better than expected for the
        shots taken. Click a player to load their court above.
      </p>
      <svg width={width} height={height} className={styles.quadrantSvg}>
        <line x1={padding} y1={height / 2} x2={width - padding} y2={height / 2} stroke="var(--line-strong)" />
        <line x1={width / 2} y1={padding} x2={width / 2} y2={height - padding} stroke="var(--line-strong)" />
        {points.map((p) => {
          const [cx, cy] = toPx(p.shot_selection, p.shot_making);
          const isSelected = p.player_id === selectedPlayerId;
          return (
            <circle
              key={p.player_id}
              cx={cx}
              cy={cy}
              r={isSelected ? 5 : 3}
              fill={isSelected ? "var(--accent-orange)" : "var(--accent-cyan)"}
              opacity={isSelected ? 1 : 0.5}
              onClick={() => onSelect(p)}
              style={{ cursor: "pointer" }}
            >
              <title>{p.player_name}</title>
            </circle>
          );
        })}
      </svg>
    </div>
  );
}
