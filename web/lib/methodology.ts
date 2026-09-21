/**
 * Types and loaders for the methodology page's per-feature eval data.
 * Reads the same exported JSON each feature's own view is built from, so
 * this page can't drift out of sync with what the pipeline actually
 * measured — no numbers are hardcoded here.
 */

export interface CalibrationBin {
  predicted: number;
  actual: number;
  n: number;
}

export interface StyleEvals {
  career_continuity: { recall_at_k: number; k: number; n_evaluated: number };
  position_predictability: { accuracy: number; chance_accuracy: number; n_evaluated: number; n_classes: number };
  cluster_stability: { mean_ari: number; min_ari: number; n_bootstrap: number };
  comp_sanity: { hit_rate: number; checked: number; total_pairs: number };
}

export interface ShotModelEval {
  log_loss: number;
  brier_score: number;
  auc: number;
  n_validated: number;
  calibration: CalibrationBin[];
}

export interface ShotQualityEvals {
  validate_season: string;
  chosen_model: string;
  baseline_eval: ShotModelEval;
  lightgbm_eval: ShotModelEval;
  grid_parity: { n_sampled: number; max_abs_error_bytes: number; max_abs_error: number };
}

export interface GameFlowModelEval {
  log_loss: number;
  brier_score: number;
  n_validated: number;
  calibration: CalibrationBin[];
  calibration_by_time_bucket: Record<string, CalibrationBin[]>;
}

export interface GameFlowEvals {
  validate_season: string;
  chosen_model: string;
  logistic_eval: GameFlowModelEval;
  lightgbm_eval: GameFlowModelEval;
  logistic_coefficients: Record<string, number>;
  logistic_intercept: number;
  n_games_exported: number;
  n_games_skipped: number;
}

export async function loadStyleEvals(): Promise<StyleEvals> {
  return fetch("/data/style/style_evals.json").then((r) => r.json());
}

export async function loadShotQualityEvals(): Promise<ShotQualityEvals> {
  return fetch("/data/shots/shot_quality_evals.json").then((r) => r.json());
}

export async function loadGameFlowEvals(): Promise<GameFlowEvals> {
  return fetch("/data/gameflow/gameflow_evals.json").then((r) => r.json());
}

export function meanAbsCalibrationGap(bins: CalibrationBin[]): number {
  if (bins.length === 0) return 0;
  const sum = bins.reduce((acc, b) => acc + Math.abs(b.predicted - b.actual), 0);
  return sum / bins.length;
}

export const TIME_BUCKET_LABELS: Record<string, string> = {
  q1: "1st quarter",
  q2: "2nd quarter",
  q3: "3rd quarter",
  q4_early: "4th, first 10 min",
  final_2_min: "Final 2 minutes",
  overtime: "Overtime",
};
