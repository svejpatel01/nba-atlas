/**
 * Types, data loading, and client-side math for the shot quality court.
 * The hex-binning and grid-lookup math here must match
 * `pipeline/src/hub/shots/hex.py` and `grid.py` exactly — same hex size,
 * same axial-coordinate formulas, same grid bounds — since the browser
 * looks up precomputed values keyed by the same IDs/cells Python produced.
 */

export const HEX_SIZE_FT = 2.0;

export interface HexAggregate {
  player_id?: number;
  hex_id: string;
  attempts: number;
  makes: number;
  xfg_sum: number;
}

export interface QuadrantPoint {
  player_id: number;
  player_name: string;
  shot_selection: number;
  shot_making: number;
  attempts: number;
}

export interface PlayerMetrics {
  season: string;
  player_id: number;
  player_name: string;
  attempts: number;
  makes: number;
  avg_xfg: number;
  shot_selection: number;
  shot_making: number;
  fg_pct: number;
  [zoneKey: string]: number | string;
}

export interface GridMeta {
  family_order: string[];
  cell_size_ft: number;
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
  n_cells_per_family: number;
  grid_context: { period: number; seconds_left_in_period: number };
}

export const ZONE_LABELS: Record<string, string> = {
  restricted_area: "Restricted area",
  paint_non_ra: "Paint (non-RA)",
  midrange: "Midrange",
  corner3: "Corner 3",
  atb3: "Above-the-break 3",
};

export const ACTION_FAMILY_LABELS: Record<string, string> = {
  layup: "Layup",
  dunk: "Dunk",
  hook: "Hook shot",
  floater: "Floater",
  catch_and_shoot: "Catch-and-shoot",
  pull_up: "Pull-up",
  step_back: "Step-back",
  fadeaway: "Fadeaway",
  tip: "Tip-in",
  alley_oop: "Alley-oop",
};

// --- Axial hex math (must match hub/shots/hex.py) ---

function axialRound(q: number, r: number): [number, number] {
  const x = q;
  const z = r;
  const y = -x - z;
  let rx = Math.round(x);
  let ry = Math.round(y);
  let rz = Math.round(z);
  const dx = Math.abs(rx - x);
  const dy = Math.abs(ry - y);
  const dz = Math.abs(rz - z);
  if (dx > dy && dx > dz) {
    rx = -ry - rz;
  } else if (dy > dz) {
    ry = -rx - rz;
  } else {
    rz = -rx - ry;
  }
  return [rx, rz];
}

export function toAxial(xFt: number, yFt: number, hexSize = HEX_SIZE_FT): [number, number] {
  const q = ((2 / 3) * xFt) / hexSize;
  const r = ((-1 / 3) * xFt + (Math.sqrt(3) / 3) * yFt) / hexSize;
  return axialRound(q, r);
}

export function hexId(xFt: number, yFt: number, hexSize = HEX_SIZE_FT): string {
  const [q, r] = toAxial(xFt, yFt, hexSize);
  return `${q}_${r}`;
}

export function hexCenter(id: string, hexSize = HEX_SIZE_FT): [number, number] {
  const [qStr, rStr] = id.split("_");
  const q = Number.parseInt(qStr, 10);
  const r = Number.parseInt(rStr, 10);
  const x = hexSize * (1.5 * q);
  const y = hexSize * ((Math.sqrt(3) / 2) * q + Math.sqrt(3) * r);
  return [x, y];
}

// --- Grid lookup (must match hub/shots/grid.py) ---

export function classifyShotValue(xFt: number, yFt: number): 2 | 3 {
  const distance = Math.sqrt(xFt * xFt + yFt * yFt);
  const inCorner = Math.abs(xFt) >= 22.0 && yFt <= 14.0;
  return inCorner || distance >= 23.75 ? 3 : 2;
}

export function gridCellIndex(xFt: number, yFt: number, meta: GridMeta): number | null {
  if (xFt <= meta.x_min || xFt >= meta.x_max || yFt <= meta.y_min || yFt >= meta.y_max) {
    return null;
  }
  const nXCells = Math.round((meta.x_max - meta.x_min) / meta.cell_size_ft);
  const col = Math.floor((xFt - meta.x_min) / meta.cell_size_ft);
  const row = Math.floor((yFt - meta.y_min) / meta.cell_size_ft);
  return row * nXCells + col;
}

/** Looks up the quantized xFG% for one court location and action family. */
export function lookupGridXfg(
  gridBytes: Uint8Array,
  meta: GridMeta,
  xFt: number,
  yFt: number,
  actionFamily: string,
): number | null {
  const familyIdx = meta.family_order.indexOf(actionFamily);
  if (familyIdx === -1) return null;
  const cellIdx = gridCellIndex(xFt, yFt, meta);
  if (cellIdx === null) return null;
  const byteIdx = familyIdx * meta.n_cells_per_family + cellIdx;
  return gridBytes[byteIdx] / 255;
}

// --- Data loading ---

export async function loadGrid(): Promise<{ bytes: Uint8Array; meta: GridMeta }> {
  const [buf, meta] = await Promise.all([
    fetch("/data/shots/xfg_grid.bin").then((r) => r.arrayBuffer()),
    fetch("/data/shots/xfg_grid_meta.json").then((r) => r.json()),
  ]);
  return { bytes: new Uint8Array(buf), meta };
}

export async function loadQuadrant(season: string): Promise<QuadrantPoint[]> {
  return fetch(`/data/shots/shot_quadrant_${season}.json`).then((r) => r.json());
}

export async function loadPlayerMetrics(season: string): Promise<PlayerMetrics[]> {
  return fetch(`/data/shots/player_metrics_${season}.json`).then((r) => r.json());
}

export async function loadLeagueHex(season: string): Promise<HexAggregate[]> {
  return fetch(`/data/shots/league_hex_${season}.json`).then((r) => r.json());
}

export async function loadPlayerHex(season: string, playerId: number): Promise<HexAggregate[]> {
  const shard = playerId % 32;
  const all: HexAggregate[] = await fetch(`/data/shots/shot_hexes_${season}_${shard}.json`).then(
    (r) => r.json(),
  );
  return all.filter((h) => h.player_id === playerId);
}
