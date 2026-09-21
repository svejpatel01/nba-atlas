/**
 * Client-side reimplementation of the win-probability model: a dot product
 * and a sigmoid (docs/game-flow-spec.md). This is what makes a future live
 * win-probability feature possible without a server round trip per update
 * — the whole reason logistic regression shipped over LightGBM despite a
 * slightly worse final-2-minutes calibration (see docs/decisions.md's
 * Phase 5 milestone 2 entry).
 *
 * Coefficients are trained in `hub.gameflow.model` and shipped in
 * `gameflow_evals.json`, not hardcoded here, so a retrained model's
 * coefficients take effect without a code change. Parity with the real
 * Python model (`hub.gameflow.model.predict_proba`) is checked in
 * win-probability.test.ts against reference values generated live from the
 * trained model, matching the pattern used for the shot-quality grid.
 */

export interface WinProbabilityCoefficients {
  margin: number;
  margin_time_decay: number;
  elo_diff_time_scaled: number;
  possession_indicator: number;
  intercept: number;
}

export interface GameStateFeatures {
  margin: number;
  margin_time_decay: number;
  elo_diff_time_scaled: number;
  possession_indicator: number;
}

export function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

/** P(home team wins), given the same four features used to train the
 * Python model — order doesn't matter here since each is multiplied by
 * its own named coefficient, unlike a raw positional dot product.
 */
export function predictWinProb(
  features: GameStateFeatures,
  coefficients: WinProbabilityCoefficients,
): number {
  const z =
    coefficients.margin * features.margin +
    coefficients.margin_time_decay * features.margin_time_decay +
    coefficients.elo_diff_time_scaled * features.elo_diff_time_scaled +
    coefficients.possession_indicator * features.possession_indicator +
    coefficients.intercept;
  return sigmoid(z);
}

export async function loadWinProbabilityCoefficients(): Promise<WinProbabilityCoefficients> {
  const evals: { logistic_coefficients: Omit<WinProbabilityCoefficients, "intercept">; logistic_intercept: number } =
    await fetch("/data/gameflow/gameflow_evals.json").then((r) => r.json());
  return { ...evals.logistic_coefficients, intercept: evals.logistic_intercept };
}
