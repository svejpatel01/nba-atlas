/**
 * Types and data loading for the game flow view. `series` points are
 * `[seconds_elapsed, home_win_prob, home_score, away_score]` — extended
 * from the spec's 2-tuple to carry score, since the UI spec's hover-
 * scrubbing requirement ("shows the exact score and clock at that point")
 * needs it at every point, not just at `top_plays` (see
 * docs/decisions.md's Phase 5 milestone 3 entry). Quarter-boundary and
 * period-length constants below must match `hub/gameflow/parse.py`.
 */

export const REGULATION_PERIODS = 4;
export const REGULATION_PERIOD_SECONDS = 12 * 60;
export const OT_PERIOD_SECONDS = 5 * 60;
export const REGULATION_SECONDS = REGULATION_PERIODS * REGULATION_PERIOD_SECONDS;

export interface GameIndexEntry {
  game_id: string;
  date: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  excitement: number;
  comeback_factor: number;
}

export interface TopPlay {
  description: string;
  seconds_elapsed: number;
  home_score: number;
  away_score: number;
  wp_change: number;
}

export type SeriesPoint = [seconds_elapsed: number, home_win_prob: number, home_score: number, away_score: number];

export interface GameBundle {
  game_id: string;
  series: SeriesPoint[];
  top_plays: TopPlay[];
  pregame_elo: { home: number; away: number };
}

export function monthKeyFromDate(date: string): string {
  return date.slice(0, 7);
}

/** "1234.5 seconds elapsed" -> "Q3 4:56" (or "OT2 1:23" past regulation). */
export function formatGameClock(secondsElapsed: number): string {
  if (secondsElapsed >= REGULATION_SECONDS) {
    const otElapsed = secondsElapsed - REGULATION_SECONDS;
    const otIndex = Math.floor(otElapsed / OT_PERIOD_SECONDS) + 1;
    const intoOt = otElapsed % OT_PERIOD_SECONDS;
    const remaining = Math.max(0, OT_PERIOD_SECONDS - intoOt);
    return `OT${otIndex} ${formatClock(remaining)}`;
  }
  const period = Math.floor(secondsElapsed / REGULATION_PERIOD_SECONDS) + 1;
  const intoPeriod = secondsElapsed % REGULATION_PERIOD_SECONDS;
  const remaining = Math.max(0, REGULATION_PERIOD_SECONDS - intoPeriod);
  return `Q${period} ${formatClock(remaining)}`;
}

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function quarterBoundaries(maxSecondsElapsed: number): number[] {
  const boundaries = [REGULATION_PERIOD_SECONDS, 2 * REGULATION_PERIOD_SECONDS, 3 * REGULATION_PERIOD_SECONDS];
  let t = REGULATION_SECONDS;
  while (t < maxSecondsElapsed) {
    boundaries.push(t);
    t += OT_PERIOD_SECONDS;
  }
  return boundaries;
}

export async function loadGamesIndex(season: string): Promise<GameIndexEntry[]> {
  return fetch(`/data/gameflow/games_${season}.json`).then((r) => r.json());
}

export async function loadMonthlyBundle(season: string, monthKey: string): Promise<GameBundle[]> {
  return fetch(`/data/gameflow/gameflow_${season}_${monthKey}.json`).then((r) => r.json());
}

export async function loadGameBundle(
  season: string,
  date: string,
  gameId: string,
): Promise<GameBundle | null> {
  const bundle = await loadMonthlyBundle(season, monthKeyFromDate(date));
  return bundle.find((g) => g.game_id === gameId) ?? null;
}
