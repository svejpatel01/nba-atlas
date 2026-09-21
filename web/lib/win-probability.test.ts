import { describe, expect, it } from "vitest";
import { predictWinProb, sigmoid, type WinProbabilityCoefficients } from "./win-probability";

// Coefficients and reference win_prob values generated live from the actual
// trained model (hub.gameflow.model.fit_logistic + predict_proba, run
// against the real event-level feature set) — not hand-derived — matching
// the parity-test pattern already used for the shot-quality grid
// (shot-quality.test.ts). Sampled across every calibration time bucket
// (Q1 through overtime) plus a few hand-picked edge cases (a tied/neutral
// state, and blowout margins at each extreme).
const COEFFICIENTS: WinProbabilityCoefficients = {
  margin: -0.017553343637163456,
  margin_time_decay: 5.197699500268748,
  elo_diff_time_scaled: 0.007339541844282195,
  possession_indicator: 0.048136291258735704,
  intercept: -0.13956014899091998,
};

const REFERENCE_SAMPLES: { features: Omit<WinProbabilityCoefficients, "intercept">; win_prob: number }[] = [
  {
    features: { margin: 9.0, margin_time_decay: 0.19188936716225313, elo_diff_time_scaled: -61.010932303263246, possession_indicator: -1.0 },
    win_prob: 0.550802696927259,
  },
  {
    features: { margin: 2.0, margin_time_decay: 0.03804179284542668, elo_diff_time_scaled: 344.5092415347426, possession_indicator: 1.0 },
    win_prob: 0.9308447967722224,
  },
  {
    features: { margin: 0.0, margin_time_decay: 0.0, elo_diff_time_scaled: 88.41213034718085, possession_indicator: 1.0 },
    win_prob: 0.6358694163574845,
  },
  {
    features: { margin: -3.0, margin_time_decay: -0.06624276084382791, elo_diff_time_scaled: -26.857757726798972, possession_indicator: 1.0 },
    win_prob: 0.3588871666503157,
  },
  {
    features: { margin: -3.0, margin_time_decay: -0.06961699976224635, elo_diff_time_scaled: 179.37015604780092, possession_indicator: -1.0 },
    win_prob: 0.6941535713798669,
  },
  {
    features: { margin: -1.0, margin_time_decay: -0.023287321641631116, elo_diff_time_scaled: -71.19140852615813, possession_indicator: -1.0 },
    win_prob: 0.3071034775639136,
  },
  {
    features: { margin: -6.0, margin_time_decay: -0.17066403719657228, elo_diff_time_scaled: 78.43338305308447, possession_indicator: -1.0 },
    win_prob: 0.40280968044618604,
  },
  {
    features: { margin: 1.0, margin_time_decay: 0.02634316848869161, elo_diff_time_scaled: 77.7903397280644, possession_indicator: 1.0 },
    win_prob: 0.6454028011945175,
  },
  {
    features: { margin: -2.0, margin_time_decay: -0.06776741475716971, elo_diff_time_scaled: 11.35769277586821, possession_indicator: 1.0 },
    win_prob: 0.4194110468825276,
  },
  {
    features: { margin: -23.0, margin_time_decay: -1.0952380952380953, elo_diff_time_scaled: 19.78323377278899, possession_indicator: -1.0 },
    win_prob: 0.004813583935676856,
  },
  {
    features: { margin: 10.0, margin_time_decay: 0.430730492253948, elo_diff_time_scaled: 17.1605653349447, possession_indicator: 1.0 },
    win_prob: 0.8906892694606083,
  },
  {
    features: { margin: 14.0, margin_time_decay: 1.2094157958139042, elo_diff_time_scaled: -4.162328505957111, possession_indicator: 1.0 },
    win_prob: 0.9973178735682967,
  },
  {
    features: { margin: 3.0, margin_time_decay: 0.5495574790854837, elo_diff_time_scaled: 1.0988836205909958, possession_indicator: 1.0 },
    win_prob: 0.9382206533867317,
  },
  {
    features: { margin: -21.0, margin_time_decay: -2.424871130596428, elo_diff_time_scaled: 0.439524156718347, possession_indicator: 1.0 },
    win_prob: 4.4467652069621385e-6,
  },
  {
    features: { margin: -1.0, margin_time_decay: -0.3333333333333333, elo_diff_time_scaled: 0.24794392671000007, possession_indicator: -1.0 },
    win_prob: 0.1300077994976511,
  },
  {
    features: { margin: 7.0, margin_time_decay: 1.3112201362143716, elo_diff_time_scaled: 0.6342918284377618, possession_indicator: 1.0 },
    win_prob: 0.9986491728025864,
  },
  {
    features: { margin: 1.0, margin_time_decay: 0.08058229640253803, elo_diff_time_scaled: 0.31095521950641114, possession_indicator: 1.0 },
    win_prob: 0.5774093863172177,
  },
  {
    features: { margin: -6.0, margin_time_decay: -1.8605210188381267, elo_diff_time_scaled: 1.0384736244474322, possession_indicator: -1.0 },
    win_prob: 5.8572678807534956e-5,
  },
  // tied, no possession/elo signal — the intercept alone should govern this
  {
    features: { margin: 0.0, margin_time_decay: 0.0, elo_diff_time_scaled: 0.0, possession_indicator: 0.0 },
    win_prob: 0.4651664822119321,
  },
  // extreme blowout, home team dominant — should saturate to (numerically) 1
  {
    features: { margin: 30.0, margin_time_decay: 25.0, elo_diff_time_scaled: 150.0, possession_indicator: 1.0 },
    win_prob: 1.0,
  },
  // extreme blowout, away team dominant — should saturate toward 0
  {
    features: { margin: -25.0, margin_time_decay: -20.0, elo_diff_time_scaled: -150.0, possession_indicator: -1.0 },
    win_prob: 3.0499650952949282e-46,
  },
];

describe("sigmoid", () => {
  it("is 0.5 at zero", () => {
    expect(sigmoid(0)).toBe(0.5);
  });

  it("saturates toward 0 and 1 at the extremes", () => {
    expect(sigmoid(-50)).toBeLessThan(1e-10);
    expect(sigmoid(50)).toBeGreaterThan(1 - 1e-10);
  });
});

describe("predictWinProb: parity with hub.gameflow.model.predict_proba", () => {
  it.each(REFERENCE_SAMPLES)(
    "matches the trained Python model for margin=$features.margin",
    ({ features, win_prob }) => {
      const predicted = predictWinProb(features, COEFFICIENTS);
      expect(predicted).toBeCloseTo(win_prob, 6);
    },
  );
});
