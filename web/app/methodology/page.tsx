"use client";

import { useEffect, useState } from "react";
import {
  loadGameFlowEvals,
  loadShotQualityEvals,
  loadStyleEvals,
  meanAbsCalibrationGap,
  TIME_BUCKET_LABELS,
  type CalibrationBin,
  type GameFlowEvals,
  type ShotQualityEvals,
  type StyleEvals,
} from "../../lib/methodology";
import ArchitectureDiagram from "./ArchitectureDiagram";
import styles from "./methodology.module.css";

const BUDGETS: [string, string][] = [
  ["Landing page JavaScript", "Under 150 KB gzipped"],
  ["Style map data file", "Under 2 MB gzipped"],
  ["Shot court: one player shard", "Under 300 KB gzipped; xFG grid under 100 KB"],
  ["Game flow: one monthly bundle", "Under 1 MB gzipped"],
  ["Worker CPU per request", "Under 5 ms"],
  ["Workers AI", "Under 10,000 neurons/day, including evals"],
  ["KV writes", "Under 500/day"],
  ["Nightly refresh", "Under 15 minutes"],
];

function CalibrationBars({ bins, label }: { bins: CalibrationBin[]; label?: string }) {
  return (
    <div className={styles.calibrationWrap}>
      {label && <h4>{label}</h4>}
      {bins.map((b, i) => (
        <div key={i} className={styles.calibrationRow}>
          <span className={styles.calibrationLabel}>{(b.predicted * 100).toFixed(0)}% bin</span>
          <div className={styles.calibrationBarTrack}>
            <div className={styles.calibrationBarPredicted} style={{ width: `${b.predicted * 100}%` }} />
          </div>
          <div className={styles.calibrationBarTrack}>
            <div className={styles.calibrationBarActual} style={{ width: `${b.actual * 100}%` }} />
          </div>
          <span className={styles.calibrationLabel}>n={b.n}</span>
        </div>
      ))}
      <div className={styles.calibrationLegend}>
        <span>
          <span className={styles.legendDot} style={{ background: "var(--fg-dim)" }} />
          predicted
        </span>
        <span>
          <span className={styles.legendDot} style={{ background: "var(--accent-cyan)" }} />
          actual
        </span>
      </div>
    </div>
  );
}

export default function MethodologyPage() {
  const [style, setStyle] = useState<StyleEvals | null>(null);
  const [shots, setShots] = useState<ShotQualityEvals | null>(null);
  const [gameflow, setGameflow] = useState<GameFlowEvals | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([loadStyleEvals(), loadShotQualityEvals(), loadGameFlowEvals()])
      .then(([s, sh, g]) => {
        setStyle(s);
        setShots(sh);
        setGameflow(g);
      })
      .catch(() => setError("Some eval data failed to load — numbers below may be incomplete."));
  }, []);

  return (
    <main className={styles.page}>
      <div className={styles.intro}>
        <h1>Methodology</h1>
        <p>
          Every number on this page is read live from the same exported JSON each feature&apos;s
          own view is built from — nothing here is hand-typed separately from the pipeline that
          produced it. Full narrative decision log: `docs/decisions.md` in the repo.
        </p>
        <p className={styles.dataThrough}>Data through 2026-04-12 (2015-16 through 2025-26 regular seasons).</p>
      </div>

      {error && <p className={styles.gapNote}>{error}</p>}

      <section className={styles.section}>
        <h2>Architecture</h2>
        <p className={styles.sectionIntro}>
          All heavy compute — fetching, feature engineering, model training — runs offline on the
          author&apos;s own machine. The deployed site is precomputed static files plus one thin
          Cloudflare Worker that only handles <code>/api/ask</code>. Data never goes into git;
          `make deploy` copies the latest exports into the static assets folder and runs `wrangler
          deploy` directly from the author&apos;s machine.
        </p>
        <ArchitectureDiagram />
      </section>

      <section className={styles.section}>
        <h2>Data sources and season coverage</h2>
        <p className={styles.sectionIntro}>
          Every table is fetched from stats.nba.com via the `nba_api` Python library, throttled to
          about one request per second and fully cached so a run can be interrupted and resumed.
          Box scores, season totals, and shot charts cover 2015-16 through 2025-26. Play-by-play
          (used for game flow) covers the three most recent completed seasons: 2023-24 through
          2025-26.
        </p>
        <ul className={styles.limitationsList}>
          <li>
            10 games (0.08% of 13,199) are missing from the canonical games table: for these
            specific games, `LeagueGameLog` reports both teams as playing away, so there&apos;s no
            reliable way to recover which team was actually home. Excluded rather than guessed.
          </li>
          <li>
            Play-by-play events are occasionally logged out of true chronological order (duplicate
            or retroactively-corrected rows, ~1.25% of all events) — detected and dropped by a
            monotonicity check in the game flow parser rather than trusted at face value.
          </li>
        </ul>
      </section>

      <section className={styles.section}>
        <h2>Features, models, and evals</h2>
        <p className={styles.sectionIntro}>
          One section per view: what it models, which approach shipped and why, and the real
          evaluation numbers behind it.
        </p>

        <div className={styles.featureBlock}>
          <h3>Player style map</h3>
          <p>
            Every player-season (2015-16 onward) placed on a 2D map by playing style — shot diet,
            role, rebounding and defense, self-creation, ball handling, shooting mode, touch
            location, and play types — via PCA for the underlying vector space, a Gaussian mixture
            for archetypes, and UMAP purely for 2D layout. Nearest-neighbor comps run as a
            brute-force cosine search entirely in the browser.
          </p>
          {!style && <p className={styles.loading}>Loading eval data…</p>}
          {style && (
            <div className={styles.statRow}>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Career continuity recall@{style.career_continuity.k}</span>
                <span className={styles.statValue}>{(style.career_continuity.recall_at_k * 100).toFixed(0)}%</span>
                <span className={styles.statSub}>n={style.career_continuity.n_evaluated}</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Position predictability</span>
                <span className={styles.statValue}>{(style.position_predictability.accuracy * 100).toFixed(0)}%</span>
                <span className={styles.statSub}>
                  vs. {(style.position_predictability.chance_accuracy * 100).toFixed(0)}% chance ({style.position_predictability.n_classes} classes)
                </span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Cluster stability (ARI)</span>
                <span className={styles.statValue}>{style.cluster_stability.mean_ari.toFixed(2)}</span>
                <span className={styles.statSub}>min {style.cluster_stability.min_ari.toFixed(2)} across {style.cluster_stability.n_bootstrap} bootstraps</span>
              </div>
              <div className={styles.stat}>
                <span className={styles.statLabel}>Hand-checked comp sanity</span>
                <span className={styles.statValue}>{(style.comp_sanity.hit_rate * 100).toFixed(0)}%</span>
                <span className={styles.statSub}>{style.comp_sanity.checked}/{style.comp_sanity.total_pairs} pairs matched author judgment</span>
              </div>
            </div>
          )}
          <p>
            <strong>Limitation:</strong> the 30% hand-checked comp sanity rate reads low in
            isolation — it&apos;s measuring exact agreement with one author&apos;s subjective sense
            of a &ldquo;good comp,&rdquo; a much stricter bar than the map being generally sensible (most
            near-misses, like Curry↔Lillard or Giannis↔LeBron, are defensible archetype
            neighbors, just not the single comp the author had in mind).
          </p>
        </div>

        <div className={styles.featureBlock}>
          <h3>Ask the box score</h3>
          <p>
            Plain-English questions are translated to a single validated SQL query by Cloudflare
            Workers AI (<code>llama-3.3-70b-instruct</code>, with 8B/3B fallbacks if the primary
            model is ever retired), then executed against real Parquet tables entirely in the
            browser via DuckDB-WASM. The same SQL guard (allowlisted tables, single
            SELECT/WITH statement, no file or network access, forced row limit) runs on both the
            Worker before caching a query and the browser before executing it.
          </p>
          <div className={styles.statRow}>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Model</span>
              <span className={styles.statValue}>llama-3.3-70b</span>
              <span className={styles.statSub}>8B model reproducibly refused recent-season questions</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Measured cost</span>
              <span className={styles.statValue}>34.1 neurons/question</span>
              <span className={styles.statSub}>~290 questions/day of headroom on the free allocation</span>
            </div>
            <div className={styles.stat}>
              <span className={styles.statLabel}>Daily budget</span>
              <span className={styles.statValue}>250 questions</span>
              <span className={styles.statSub}>1/minute per visitor</span>
            </div>
          </div>
          <p className={styles.gapNote}>
            Not yet measured: golden-set execution accuracy (`evals/ask/golden.jsonl`, ~60
            questions across easy/medium/hard) and Worker CPU time per request. Both are flagged
            open in `docs/decisions.md` rather than reported with a made-up number — the model
            choice above is based on manual spot checks, not the full eval, and may change once
            that eval exists.
          </p>
        </div>

        <div className={styles.featureBlock}>
          <h3>Shot quality court</h3>
          <p>
            An expected field-goal probability (xFG) model — what an average player would shoot
            from a given location, situation, and shot type — trained on every field goal attempt
            since 2015-16. A LightGBM classifier was compared against a logistic-regression
            baseline with distance/angle splines; the model isn&apos;t shipped directly, only a
            precomputed lookup grid the browser reads at 1-foot resolution per action family.
          </p>
          {shots && (
            <>
              <table className={styles.modelTable}>
                <thead>
                  <tr>
                    <th></th>
                    <th>Log loss</th>
                    <th>Brier</th>
                    <th>AUC</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className={shots.chosen_model === "logistic" ? styles.chosen : undefined}>
                    <td>Logistic baseline</td>
                    <td>{shots.baseline_eval.log_loss.toFixed(4)}</td>
                    <td>{shots.baseline_eval.brier_score.toFixed(4)}</td>
                    <td>{shots.baseline_eval.auc.toFixed(4)}</td>
                  </tr>
                  <tr className={shots.chosen_model === "lightgbm" ? styles.chosen : undefined}>
                    <td>LightGBM</td>
                    <td>{shots.lightgbm_eval.log_loss.toFixed(4)}</td>
                    <td>{shots.lightgbm_eval.brier_score.toFixed(4)}</td>
                    <td>{shots.lightgbm_eval.auc.toFixed(4)}</td>
                  </tr>
                </tbody>
              </table>
              <p>
                Shipped <strong>{shots.chosen_model}</strong> — validated on {shots.validate_season}
                , holding out that season from training. Grid parity: {shots.grid_parity.n_sampled}{" "}
                sampled cells, max error {shots.grid_parity.max_abs_error_bytes} (of 255 quantization
                levels) between the exported grid and direct model predictions.
              </p>
              <CalibrationBars bins={shots.lightgbm_eval.calibration} label="Calibration — chosen model, league-wide" />
            </>
          )}
          <p>
            <strong>Limitation:</strong> no defender-distance data exists in public shot logs, so
            the model can&apos;t separate a contested layup from a wide-open one — <code>layup</code>
            is the one action family with a materially wider calibration gap than the rest.
          </p>
        </div>

        <div className={styles.featureBlock}>
          <h3>Game flow</h3>
          <p>
            Win probability through every game since 2023-24, from play-by-play events plus a
            FiveThirtyEight-style Elo rating (K=20, +75 home-court points, 30% regression toward
            the mean each season) computed from the full 2015-16 onward history. No betting-line
            data anywhere in the pipeline.
          </p>
          {gameflow && (
            <>
              <table className={styles.modelTable}>
                <thead>
                  <tr>
                    <th></th>
                    <th>Log loss</th>
                    <th>Brier</th>
                  </tr>
                </thead>
                <tbody>
                  <tr className={gameflow.chosen_model === "logistic" ? styles.chosen : undefined}>
                    <td>Logistic</td>
                    <td>{gameflow.logistic_eval.log_loss.toFixed(4)}</td>
                    <td>{gameflow.logistic_eval.brier_score.toFixed(4)}</td>
                  </tr>
                  <tr className={gameflow.chosen_model === "lightgbm" ? styles.chosen : undefined}>
                    <td>LightGBM (monotonic on margin)</td>
                    <td>{gameflow.lightgbm_eval.log_loss.toFixed(4)}</td>
                    <td>{gameflow.lightgbm_eval.brier_score.toFixed(4)}</td>
                  </tr>
                </tbody>
              </table>
              <p>
                Shipped <strong>{gameflow.chosen_model}</strong> — both models calibrate within
                ~{(meanAbsCalibrationGap(gameflow.logistic_eval.calibration) * 100).toFixed(1)}pp on
                average, and LightGBM&apos;s final-2-minutes edge (
                {(meanAbsCalibrationGap(gameflow.logistic_eval.calibration_by_time_bucket.final_2_min ?? []) * 100).toFixed(1)}
                pp vs.{" "}
                {(meanAbsCalibrationGap(gameflow.lightgbm_eval.calibration_by_time_bucket.final_2_min ?? []) * 100).toFixed(1)}
                pp gap) wasn&apos;t large enough to give up logistic regression&apos;s
                client-side portability — the whole point being a future live win-probability
                feature with zero server round trips, reimplemented in TypeScript and checked
                against the Python model to a 1e-6 tolerance.
              </p>
              {Object.entries(gameflow.logistic_eval.calibration_by_time_bucket).map(([bucket, bins]) => (
                <CalibrationBars key={bucket} bins={bins} label={`Calibration — ${TIME_BUCKET_LABELS[bucket] ?? bucket}`} />
              ))}
            </>
          )}
          <p>
            <strong>Limitation:</strong> Elo is built from final scores only — no injuries, rest,
            or in-season roster changes. Possession is derived from event sequences, not exposed
            directly by the API, so it can occasionally misfire on unusual sequences (technical
            fouls, replay reviews).
          </p>
        </div>
      </section>

      <section className={styles.section}>
        <h2>How this stays free</h2>
        <p className={styles.sectionIntro}>
          The whole site runs on Cloudflare&apos;s free plan. These are the budgets that shaped
          nearly every low-compute design choice above — precomputed grids instead of shipping
          models, caching before calling an LLM, static assets over server rendering.
        </p>
        <table className={styles.budgetTable}>
          <thead>
            <tr>
              <th>Item</th>
              <th>Budget</th>
            </tr>
          </thead>
          <tbody>
            {BUDGETS.map(([item, budget]) => (
              <tr key={item}>
                <td>{item}</td>
                <td>{budget}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className={styles.section}>
        <h2>Versions</h2>
        <ul className={styles.versionsList}>
          <li>Ask the box score schema version: 1</li>
          <li>Data through: 2026-04-12</li>
          <li>Shot quality model: {shots?.chosen_model ?? "loading…"}, validated on {shots?.validate_season ?? "…"}</li>
          <li>Game flow model: {gameflow?.chosen_model ?? "loading…"}, validated on {gameflow?.validate_season ?? "…"}</li>
        </ul>
      </section>

      <section className={styles.section}>
        <h2>Legal and brand hygiene</h2>
        <p className={styles.sectionIntro}>
          Noncommercial portfolio project, not affiliated with or endorsed by the NBA. Data
          sourced from stats.nba.com. No team or league logos are used.
        </p>
      </section>
    </main>
  );
}
