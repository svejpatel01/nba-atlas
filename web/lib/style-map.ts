/**
 * Types and data loading for the player style map. Nearest-neighbor search
 * is a brute-force cosine scan over ~4,000 short vectors (a few ms, per
 * PLAN.md — no precomputation needed).
 */

export interface StyleMapPoint {
  player_id: number;
  name: string;
  season: string;
  team_id: number;
  team: string | null;
  minutes: number;
  provisional: boolean;
  x: number;
  y: number;
  vec: number[];
  arch: number[];
  fingerprint: Record<string, number>;
  panel: {
    pts_per36: number | null;
    ts_pct: number | null;
    height: string | null;
    position: string | null;
  };
}

export interface Archetype {
  id: number;
  name: string;
  description: string;
  color: string;
  top_features: { feature: string; z_score: number }[];
  n_player_seasons: number;
}

export interface StyleModelMeta {
  feature_names: string[];
  feature_groups: Record<string, string[]>;
  pca_components: number;
  pca_explained_variance: number;
  gmm_components: number;
  model_version: number;
  data_through: string;
}

export async function loadStyleMapData(): Promise<{
  points: StyleMapPoint[];
  archetypes: Archetype[];
  meta: StyleModelMeta;
}> {
  const [points, archetypes, meta] = await Promise.all([
    fetch("/data/style/style_map_modern.json").then((r) => r.json()),
    fetch("/data/style/archetypes.json").then((r) => r.json()),
    fetch("/data/style/style_model_meta.json").then((r) => r.json()),
  ]);
  return { points, archetypes, meta };
}

/** Human-readable labels for the fingerprint's feature-group keys. */
export const GROUP_LABELS: Record<string, string> = {
  shot_diet: "Shot selection",
  role: "Playmaking role",
  rebound_defense: "Rebounding & defense",
  self_creation: "Creating own shot",
  ball_handling: "Ball handling",
  shooting_mode: "Shot type",
  touch_location: "Where they touch it",
  play_types: "Play style",
};

/** Converts a group's z-score into a plain-language comparison to a league-
 * average player that season — the raw number ("Shot Diet: 0.1") means
 * nothing without stats background, so this is what the UI shows by
 * default; the exact z-score is still available in a tooltip for anyone
 * who wants it.
 */
export function describeZScore(z: number): string {
  const magnitude = Math.abs(z);
  const more = z >= 0;
  if (magnitude < 0.25) return "About average";
  if (magnitude < 0.75) return more ? "Somewhat more than average" : "Somewhat less than average";
  if (magnitude < 1.5) return more ? "More than average" : "Less than average";
  return more ? "Much more than average" : "Much less than average";
}

export function archmax(point: StyleMapPoint): number {
  let best = 0;
  for (let i = 1; i < point.arch.length; i++) {
    if (point.arch[i] > point.arch[best]) best = i;
  }
  return best;
}

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let na = 0;
  let nb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    na += a[i] * a[i];
    nb += b[i] * b[i];
  }
  const denom = Math.sqrt(na) * Math.sqrt(nb);
  return denom === 0 ? 0 : dot / denom;
}

export interface NeighborOptions {
  k?: number;
  sameEraOnly?: boolean;
  hideOwnSeasons?: boolean;
}

/** Brute-force cosine nearest neighbors of `points[queryIndex]` among `points`. */
export function findNearestNeighbors(
  points: StyleMapPoint[],
  queryIndex: number,
  options: NeighborOptions = {},
): { point: StyleMapPoint; similarity: number }[] {
  const { k = 8, hideOwnSeasons = false } = options;
  const query = points[queryIndex];
  const results: { point: StyleMapPoint; similarity: number }[] = [];
  for (let i = 0; i < points.length; i++) {
    if (i === queryIndex) continue;
    if (hideOwnSeasons && points[i].player_id === query.player_id) continue;
    results.push({ point: points[i], similarity: cosineSimilarity(query.vec, points[i].vec) });
  }
  results.sort((a, b) => b.similarity - a.similarity);
  return results.slice(0, k);
}
