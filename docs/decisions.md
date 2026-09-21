# Decisions log

Short entries for notable choices and corrections, newest first.

## 2026-09-18 — Added a site-wide nav bar: methodology was unreachable from any feature page

Root cause of "I don't see the methodology page": there was no persistent
navigation anywhere in the app (`web/app/layout.tsx` rendered only
`{children}`). The only link to `/methodology` in the entire site was one
line of text at the bottom of the homepage — landing on any feature page
directly (a shared link, a bookmark) left no way back to it, or to any
other feature, without hand-editing the URL.

Added `SiteNav` (`web/app/SiteNav.tsx`), a small client component in the
root layout with links to all four features plus Home and Methodology,
active-page highlighted via `usePathname`. Removed the now-redundant
standalone link from the homepage. Verified by loading `/shot-quality`
directly and clicking through to Methodology from the nav — works, zero
console errors.

## 2026-09-18 — Ask the box score verified end-to-end in browser; methodology page built

**Ask verification.** Drove the redesigned chat UI live, including a real
free-text question through the actual deployed pipeline (Worker →
Workers AI `llama-3.3-70b` → SQL guard → DuckDB-WASM), now that `wrangler
login` is authenticated. Confirmed: gallery examples fire zero network
calls; the SQL guard's adversarial test suite (multiple statements, hidden
keywords in comments, file/URL reads, missing LIMIT) is comprehensive and
passing; the refusal path returns the exact canned message for an
off-topic question; the real free-text round trip works (2.87s, real SQL,
real results) and correctly triggers the 1/minute cooldown UI afterward.
Zero console/network errors throughout.

Also chased down an alarming-looking result from a gallery example —
"Bam Adebayo, 83 points" — before writing it off. Confirmed the game's
individual player scores sum exactly to the team total (150), so it's
internally consistent data, not a pipeline bug; just an unusual value in
the underlying (simulated-future-date) data source.

**Two acceptance criteria from PLAN.md's Feature 2 remain unmet, flagged
rather than faked**: golden-set execution accuracy (`evals/ask/golden.jsonl`
was never written — this was already flagged open in the 2026-09-17 model-
choice entry below, still true) and Worker CPU under 5ms per request
(`wrangler dev`'s local observability API only exposes wall-clock
`duration_ms`, which includes the Workers AI network wait — real CPU time
needs a production deployment and `wrangler tail` or the dashboard).

**Methodology page.** Built out the previously-stub `/methodology` page for
real: an architecture diagram (hand-drawn SVG, no diagramming library,
mirroring PLAN.md's mermaid flowchart), data sources and season coverage
(including both real limitations found this week — the 10-game MATCHUP gap
and the ~1.25% out-of-order PBP events), a section per feature with numbers
read live at runtime from each feature's actual exported eval JSON
(`style_evals.json`, `shot_quality_evals.json`, `gameflow_evals.json` —
nothing hardcoded, so the page can't drift from what the pipeline measured),
calibration-bar visualizations for shot quality and every game-flow time
bucket, the "how this stays free" budget table, and per-feature limitations.
Ask the box score's section is static text (no eval JSON exists yet) and
says so plainly rather than inventing a number for the missing golden-set
accuracy.

Left out, and worth naming rather than silently skipping: a site-wide
attribution footer and per-view Open Graph images (PLAN.md's "Shared
requirements," which span every page, not just methodology — better scoped
as a Phase 6 site-shell pass) and the landing page's four-card layout
(still the original stub).

**With this, all four features have working core functionality and a
verified browser pass.** Remaining before the design/polish pass: the
Ask golden-set eval (whenever it's prioritized), and the site-shell items
above.

## 2026-09-18 — Phase 5 milestone 5 (partial): TypeScript win-probability parity test

Built `web/lib/win-probability.ts`: a client-side reimplementation of the
shipped logistic model — a dot product over named features plus a sigmoid,
nothing more, per the spec's whole reason for shipping logistic over
LightGBM (portability to a future live-mode feature with zero server
round trips per update). Coefficients aren't hardcoded — `loadWinProbabilityCoefficients`
fetches them from `gameflow_evals.json`, so a retrained model's
coefficients take effect with no code change on the frontend.

Parity test (`win-probability.test.ts`): 21 reference `(features,
win_prob)` pairs generated live from the actual trained model
(`hub.gameflow.model.fit_logistic` + `predict_proba` run against the real
event-level feature set, not hand-derived), stratified across every
calibration time bucket plus hand-picked edge cases (a fully neutral
state, and blowout margins saturating toward 0 and 1 — one reference value
is `3.05e-46`, well inside float64 range on both sides, no overflow
mismatch risk). All 21 match to the spec's 1e-6 tolerance via
`toBeCloseTo`. Same pattern already established for the shot-quality xFG
grid's own JS/Python parity test — reference values generated from a real
model run, not asserted against hand math.

**Scope note on the rest of milestone 5**: the methodology page is
currently a single Phase 6 stub covering all four features
(`web/app/methodology/page.tsx`), and none of the other three features
have their section written yet either. Writing only game flow's slice of
it now would leave an inconsistent partial page rather than complete a
coherent one — better done as a unified Phase 6 pass once every feature's
core functionality (including Ask the box score's still-unverified
acceptance criteria) is confirmed working. Elo parameters, the
logistic-vs-LightGBM comparison, and the parity result are already fully
captured in this log (milestones 2 and 5) and in `gameflow_evals.json`, so
nothing is lost by deferring the write-up — it's assembly, not new
analysis.

With this, **all four features have their core functionality built and
tested**: player style map, ask the box score (now a chat UI), shot
quality court (browser-verified), and game flow (Elo, parser, model,
exports, UI, and TS parity all done). Remaining before `nba.svej.org`:
Ask the box score's own browser verification pass, the unified
methodology page, and the design/polish pass the user wants to do next.

## 2026-09-18 — Phase 5 milestone 4: game flow UI built; a real bug caught by actually driving it

Built the game flow view: `web/lib/gameflow.ts` (data loading, game-clock
formatting, quarter-boundary math mirroring `hub/gameflow/parse.py`'s
constants), `WinProbabilityChart.tsx` (hand-rolled SVG, no charting
library, matching the shot-quality court's approach and PLAN.md's stated
preference), and `game-flow/page.tsx` (season picker, team filter, game
search, "most exciting" / "biggest comebacks" season lists, shareable
`?season=&game=` URLs read via a mount-time effect rather than
`next/navigation`'s `useSearchParams` — avoids that hook's required
Suspense boundary for a one-time URL read on a fully static-exported
page).

**Data-contract deviation worth flagging**: PLAN.md's `series` field is a
2-tuple (`[seconds_elapsed, home_win_prob]`), but the UI spec separately
requires hover-scrubbing to show "the exact score and clock at that
point" — score isn't recoverable from a 2-tuple. Extended each point to
`[seconds_elapsed, home_win_prob, home_score, away_score]` instead of
dropping that requirement; cost is negligible (two small, slowly-changing
integers per point) against the 1MB/bundle budget — largest bundle is
still ~240KB gzipped.

**A real bug, caught only by actually loading a game and looking at the
chart** (not by any of the 3,680-game score-conservation check, which
only looks at final scores): the first game clicked in manual browser
verification showed a "top play" reading `OT1 5:00 — End of 4th Period,
+6.4pp` for a game that never went to overtime. Root cause: `PlayByPlayV3`
occasionally logs an event (in this case a duplicate/retroactively-logged
`Turnover`) whose `action_number` places it very late in the stream —
right before "End of Period" — while its own `clock` field reads a much
earlier moment (9:11 remaining in the quarter). `home_score`/`margin` for
that row are correct (derived from true stream position), but
`seconds_elapsed` — derived from the row's own clock — is not, so it
appeared to teleport backward on the time axis. Since `top_plays` are
detected by diffing consecutive rows, comparing two states that were never
really adjacent in time fabricated a large fake swing.

**Fix**: `hub.gameflow.parse.build_game_states` now tracks the maximum
`seconds_elapsed` emitted so far and drops (not re-timestamps — there's no
reliable way to know where a mis-logged event actually belongs) any row
whose own clock would move the axis backward. Re-ran the full 3,680-game
validation after the fix: still 0 score mismatches, `seconds_elapsed` now
verified monotonic in every game, and **22,841 of 1,827,122 events
(~1.25%) were dropped** — confirming this was a real, non-trivial
fraction of the data, not a one-off. Retrained and re-exported; the
logistic model's validation log loss barely moved (0.4428 → 0.4428,
essentially unchanged), consistent with these rows being rare enough not
to affect aggregate calibration but common enough to occasionally corrupt
a specific game's chart.

This is another case (alongside milestone 1's jump-ball and score-guard
fixes) where a bug only surfaced by actually running at full scale or
looking at rendered output — neither code review nor a single hand-checked
example would have caught it.

**Tests**: 1 new parser test for the dropped-row case, plus one existing
test's fixture adjusted since the new guard now subsumes its original
scenario (a same-clock, different-score case was substituted to keep
exercising the score guard specifically). 141 pipeline tests, 38 web
tests, all passing.

**Next**: milestone 5 (TypeScript parity test for the logistic model,
methodology page section covering Elo/calibration/model choice, mobile
layout pass).

## 2026-09-18 — Phase 5 milestone 1: Elo pipeline and PBP parser built; two real possession/score bugs caught by validating at scale

Started game flow (`hub.gameflow`). Kicked off a background backfill for the
missing play-by-play games (237 of 2024-25, all 1,225 of 2025-26 — the prior
cache only had 2023-24 complete plus a partial 2024-25) since it's the long
pole at the ~1 req/sec throttle; built the rest of milestone 1 against what
was already cached (2,220 games) while it ran.

**Elo (`hub.gameflow.elo`)**: standard FiveThirtyEight-style ratings from
`games.parquet`'s full history — K=20, +75 rating points of home-court
advantage applied at prediction time (not folded into the stored rating),
30% regression toward 1500 at each season boundary. No blocker here since
game-level scores for the full 2015-16 → 2025-26 span were already fetched
in Phase 1; margin-of-victory multiplier left as a later tuning question
per PLAN.md ("only keep it if it improves calibration").

**Play-by-play parser (`hub.gameflow.parse`)**: turns raw `PlayByPlayV3`
events into per-event game states (period, seconds elapsed/remaining,
score, margin, possession). `PlayByPlayV3` doesn't expose possession
directly, so it's derived from a state machine over event sequences —
documented in full in the module docstring. Two bugs the spec explicitly
warned to check for before trusting this ("possession logic is a common
source of subtle bugs") showed up only when validating past a couple of
hand-checked games and running the parser against *all* 2,220 currently
cached games, checking each one's final derived score against
`games.parquet`'s real final score:

- **Jump-ball tip winner.** The `team_id` on a "Jump Ball" event is one of
  the two jumpers' teams, not the tip recipient's — the first hand-checked
  game showed the parser seeding possession from that unreliable field
  immediately instead of waiting for whichever team acts in the next
  possession-relevant event. Fixed by leaving possession unresolved
  (`None`) through the jump ball itself.
- **Non-monotonic score snapshots.** 18 of 2,220 games (0.8%) had a final
  derived score that didn't match `games.parquet`. All 18 traced to the
  same root cause: rows appended after the true end of a period —
  technical-foul free throws logged post-hoc, "Instant Replay" review
  rows — carry the score *as of the moment being reviewed or corrected*,
  not the current game state, and can be lower than the running total even
  though their `action_number` sorts after it. Rather than special-casing
  those action types (fragile — more variants likely exist), the
  score-forward-fill now only accepts a new value if it's `>=` the running
  total, since a real NBA score is never lower than what's already been
  reached. Re-ran the full 2,220-game check after the fix: 0 mismatches.

Also checked: null-possession rate (unresolved before the opening
tip/period start) averages 0.6% of events per game, max 2.6% — small and
expected, not a sign of a broader gap.

**Tests**: 8 for `elo` (zero-sum rating changes, season-boundary
regression, home-advantage effect on rating deltas), 19 for `parse` (clock
parsing, elapsed/remaining time including overtime, and one test per
possession rule — made shot, and-1 deferral, missed-shot rebounds
both ways, turnover, jump ball, non-last free throws, the stale-score
guard). The 2,220-game score-conservation check itself isn't a committed
test (it needs `data/tables/pbp_events.parquet`, which is gitignored and
only exists after running the fetch/tables pipeline) — it was a one-off
validation pass, documented here instead.

**Update (same session): backfill landed, full scope validated, and a
separate Phase-1-era gap found along the way.** The background backfill
finished cleanly (0 warnings/skips across ~2,455 new PBP fetches). Rebuilt
the canonical tables (`make tables`) and reran the score-conservation
check against the complete scope: **3,680/3,680 validatable games, 0
mismatches** (up from 2,220 games; the 8 new milestone-1 test bugs above
were already fixed before this run, so this is confirmation at full scale,
not a new fix).

That rebuild's quality report also flipped 2 `join_integrity` checks that
had never run against this much of 2024-25/2025-26 before: 10 games (5 per
season, 0.08% of all 13,199) have PBP and shot data but no row in
`games.parquet`. Root cause, confirmed by reading `team_game_logs.parquet`
directly: `build_games` (`hub/tables/build.py`, written in Phase 1) derives
each game's home team from whichever of the two team-perspective rows has
`" vs. "` in `MATCHUP`, pairing it with the other row via an inner join.
For these 10 games specifically, **both** rows read "@" — e.g. team OKC's
own row says `"OKC @ HOU"` *and* team HOU's own row says `"HOU @ OKC"`,
each claiming to be the away team — so neither matches `" vs. "`, both
land in the "away" bucket, and the inner join silently drops the game
rather than guessing. Since the two rows actively disagree about who's
home, there's no safe reconstruction from this data alone, and at 10
games out of 13,199 it's not worth chasing further (no date/venue pattern
found — it's not confined to a neutral-site tournament game, just
scattered API inconsistency across both seasons). Left as-is: these 10
games are absent from `games.parquet` and therefore from Elo and any
gameflow exports, a limitation worth a line on the methodology page
alongside the shot-quality and possession-derivation ones already there.

**Next**: feature engineering and model training (milestone 2) — Elo,
parser, and full-scope validation are done.

## 2026-09-18 — Phase 5 milestone 2: win-probability model trained, logistic regression chosen

Built `hub.gameflow.features` (one training row per parsed event: margin,
margin/√(seconds_remaining+1), pregame Elo difference scaled by fraction of
game time remaining, a ±1/0 possession indicator, home-court folded into
Elo rather than kept as a separate raw feature per PLAN.md) and
`hub.gameflow.model` (logistic regression vs. LightGBM with a monotonic
constraint on margin and its time-decayed twin — constraining one without
the other would let non-monotonic quirks back in through the correlated
feature). Split by season: trained on 2023-24 + 2024-25 (1,202,656 rows),
validated on 2025-26 (619,223 rows) — the most recent completed season,
same convention as the shot-quality split.

| | Log loss | Brier |
|---|---|---|
| Logistic | 0.4428 | 0.1476 |
| LightGBM | 0.4409 | 0.1474 |

Both calibrate within ~1.3pp average gap across deciles league-wide, and
per PLAN.md's specific ask, checked the final-2-minutes bucket separately:
2.3pp (logistic) vs. 1.8pp (LightGBM) — LightGBM is a little better there
but not by the 1pp `MATERIAL_CALIBRATION_GAP` bar (`choose_model` weighs
this bucket on its own, not just the overall average, since the spec calls
it out as "where a model most commonly misbehaves and where visitors will
scrutinize the chart most closely"). Neither model's overall or
final-2-minute edge clears that bar, so **shipped logistic regression** —
matching the spec's default preference for a model portable to a few lines
of client-side TypeScript, needed for the stretch live-mode goal.

**A logistic coefficient sign worth flagging before it looks like a bug on
the methodology page**: `margin`'s raw coefficient came out slightly
negative (-0.0196) while `margin_time_decay`'s is strongly positive
(+5.25). This isn't a bug — `margin_time_decay` is literally
`margin / sqrt(seconds_remaining + 1)`, so the two features are highly
collinear, and unregularized-enough coefficient weight can redistribute
between correlated inputs while their *combined* effect stays correctly
monotonic (confirmed by `test_fit_logistic_predicts_higher_prob_for_bigger_home_margin`,
which checks the net prediction, not either coefficient in isolation).
Worth a one-line caveat if the raw coefficients are ever shown next to each
other on the methodology page.

**Tests**: 8 for `features` (label correctness, the three engineered
feature formulas, exclusion of games missing PBP or Elo coverage), 8 for
`model` (time-bucket assignment including the OT special case, the
monotonicity constraint holding end-to-end through `predict_proba`, and
`choose_model`'s two branches) — all synthetic/fast, no dependency on the
gitignored `data/` tables.

**Next**: milestone 3 (score the full scope, compute per-game summaries —
downsampled win-probability series, top plays, excitement index, comeback
factor — and export the game index + monthly bundles), then milestone 4
(the static chart view) and milestone 5 (TypeScript parity + methodology
page section).

## 2026-09-18 — Phase 5 milestone 3: full scope scored and exported

Built `hub.gameflow.summaries` (downsampled win-probability series — keep a
point on a >2pp swing or at least once a minute, capped at 150 points;
top-5 plays by absolute win-probability change; excitement index; comeback
factor) and `hub.gameflow.export`, which retrains the chosen model
(logistic, per milestone 2) on the *full* window rather than just the
training split before scoring — same "refit on everything once a model's
picked" pattern as shots. Added a guard that fails loudly if a future run
ever picks LightGBM instead, since only logistic has a planned TypeScript
reimplementation (milestone 5) — silently shipping a model the frontend
can't reproduce would be worse than an explicit `NotImplementedError`.

Ran the real export end to end: **3,680 games scored, 0 skipped** (the
10-game MATCHUP gap never entered the feature set in the first place, via
the inner join in `build_game_flow_features` — nothing left to skip by the
time export.py's own counter runs). `games_{season}.json` (1,230 / 1,225 /
1,225 rows, matching the known-good per-season counts) plus 21 monthly
`gameflow_{season}_{month}.json` bundles, largest gzips to ~175KB — well
inside the spec's 1MB budget.

Spot-checked the 2023-24 season opener (Nuggets ring ceremony vs. Lakers,
`0022300061`) end to end: pregame Elo (Denver 1554.5 vs. LA 1536.0, sensible
for a defending champion vs. an out-of-title-shape team), a win-probability
series that starts at 61% for Denver at tip-off and climbs to 100% by the
final buzzer they actually won, and top plays that are real, named,
correctly-signed shots from that specific game (a Jokic three swings it
+10.2pp toward Denver, a LeBron three swings it -10.1pp the other way).

**Tests**: 10 for `summaries` (series downsampling — first/last always
kept, the point cap, the per-minute floor in a blowout, the swing-trigger
case — plus top-plays ranking/ordering, excitement summing, and both
comeback-factor branches). `export.py` itself isn't unit tested, same
convention as `hub.shots.export`/`hub.style.export` — it's I/O
orchestration over the real tables, validated by actually running it
rather than mocking parquet files.

**Next**: milestone 4 (game picker + win-probability chart UI, currently
just a stub page) and milestone 5 (TypeScript parity test + methodology
page section for game flow).

## 2026-09-18 — Phase 4 complete: shot quality court verified end-to-end in browser

Drove the live view (`make worker-dev`, Playwright against headless Chromium
— `chromium-cli` wasn't installed on this machine, so scripted directly
against `node_modules`-local `playwright` instead) rather than relying on
code review alone. Verified: player search (LeBron James), season switch
(2023-24 → 2018-19 reloads the player's hex shard correctly), the diff/xFG%
color toggle, the action-family dropdown driving the click-anywhere xFG
tooltip (48% expected for a pull-up at the clicked point), the by-zone stat
table, and the 436-point shot-selection-vs-shot-making quadrant scatter.
Zero console errors throughout.

**Render timing:** 65ms from season-select change to next canvas paint,
under the 100ms budget in PLAN.md's Phase 4 acceptance criteria. All three
acceptance-criteria checkboxes for Feature 3 are now checked in `PLAN.md`
(calibration and grid parity were already numerically satisfied per the
entries below; this closes out the render-time item, which needed an actual
browser measurement rather than a code read).

## 2026-09-17 — Phase 4: shot-quality model trained, LightGBM chosen, perfect grid parity

Full run on all 2,283,747 cleaned shots (2015-16 → 2025-26), trained on
2015-16 → 2024-25, validated on 2025-26 (the most recent completed season).

| | Log loss | Brier | AUC |
|---|---|---|---|
| Logistic baseline (splines) | 0.6471 | 0.2284 | 0.6437 |
| LightGBM | 0.6431 | 0.2267 | 0.6538 |

Both calibrate within ~1-3 percentage points across deciles league-wide,
matching the spec's target. By action family, `layup` is the outlier (6.3pp
max gap) — plausibly because "layup" bundles a huge range of real difficulty
(contested vs. wide open) that the model can't separate without defender
data, exactly the limitation the spec already names. Chose **LightGBM**:
its calibration gap is materially smaller (>0.003 average absolute
gap improvement over the baseline, the threshold set in
`hub.shots.export.MATERIAL_CALIBRATION_GAP`).

**Grid parity: 0 error** (max_abs_error_bytes=0 across 2,000 sampled
cell/family pairs) — the exported quantized grid matches direct model
predictions exactly at the byte level, confirming the grid-generation code
(coordinate transform, family encoding, quantization) has no silent bugs.
Grid file is exactly 23,500 bytes (2,350 cells × 10 families), matching
PLAN.md's estimate precisely.

Per-shard hex files: ~110KB raw / ~16KB gzipped — comfortably under the
300KB gzipped per-shard budget. xFG grid 23.5KB, under the 100KB budget.

## 2026-09-17 — Phase 4: 341 shots (2015-16/2016-17 only) have no coordinates at all

Separate from the origin-coordinate finding below: 341 shots — all in
2015-16 and 2016-17, none in any later season — have `loc_x`, `loc_y`, and
`shot_distance` all null, not just zero. Unlike the origin shots, there's no
consistent signal here (no distance to fall back on), so these are dropped
in `build_shot_features`. At 0.015% of all shots this doesn't move any
metric, but it's a genuine early-API gap worth naming rather than silently
filtering — a `SplineTransformer` fit surfaced it immediately (`ValueError:
Input X contains NaN`) since sklearn refuses NaN by default.

## 2026-09-17 — Phase 4: origin-coordinate shots are real rim attempts, not errors

PLAN.md's shot-quality spec flagged shots at the exact `(0, 0)` coordinate as
"clearly invalid... sometimes indicates a data error," suggesting they be
dropped. Checked the real data first instead of dropping on the spec's
hedge alone: all ~35,246 such rows (out of 2,319,756 total, concentrated in
2020-21 onward — likely a rounding convention introduced around then) have
`shot_distance = 0` too, perfectly consistent with a genuine point-blank rim
attempt (dunk or layup right at the basket), not a contradiction that would
indicate a real coordinate error. Initially wrote the filter to drop them
per the spec's phrasing, caught it by checking real numbers before running
the model, and removed the drop — keeping ~1.5% more real, informative
training data (disproportionately dunks/point-blank layups, which the model
needs to see plenty of to calibrate the highest-value shots correctly).
Still drops the actual garbage: the 81 `action_type = "No Shot"` rows.

## 2026-09-17 — Phase 2: style map fit and evaluated; two eval-design bugs fixed live

Fit PCA (11 components, 90.7% variance) + Gaussian mixture (BIC picked k=9)
+ UMAP on 3,975 qualifying player-seasons (2015-16 → 2025-26, 500+ minutes),
37 features across all 8 spec-defined groups (shot diet, role,
rebounding/defense, self-creation, ball handling, shooting mode, touch
location, play types). Row count landed almost exactly on the spec's own
estimate ("on the order of 4,000 rows in Modern mode") — a good sign the
feature/qualification logic is right, not just coincidentally close.

**Bug found while building the feature table**: `SynergyPlayTypes` returns a
separate row per team for a traded player (no combined total row, unlike
every other stats endpoint used so far). Joining 10 play types sequentially
without deduplicating first fanned this out multiplicatively — one run
produced 23,575 "player-seasons" instead of ~4,000. Fixed by summing
possessions per player before joining (`build_play_type_features`), and
added a standing assertion in `hub.style.pipeline` that raises immediately
if any join produces duplicate `player_id` rows, so this class of bug can't
silently reappear for a different source table later.

**Two bugs found while sanity-checking the evals, not the model**:
manually inspecting real nearest neighbors (Rudy Gobert → Tyson Chandler,
DeAndre Jordan; Kevin Durant → Brandon Ingram, Khris Middleton) showed the
model working well, but the hand-written comp eval scored 0/10 hits. Root
causes were in the eval, not the model: (1) a player's own other seasons are
usually similar enough to fill most of the top-10 by themselves, crowding
out real cross-player comps — fixed by excluding a player's own seasons from
the neighbor search, matching the spec's own UI design ("hiding the
player's own other seasons" is a real toggle for exactly this reason, not
just a UX nicety). (2) Checking only the *comp's own most recent season*
against the *target's most recent season* conflates career stage with
style — Gobert's latest season here is 2025-26, but Tyson Chandler's last
qualifying season is 2018-19, so "current Gobert vs. current Chandler" was
never going to match even for a perfect model. Fixed by checking whether
*any* season of the named comp appears in the neighbor list. After both
fixes: comp sanity hit rate 3/10 — a believable, investigable number (some
of the 10 hand-picked pairs are genuinely loose comps, e.g. Curry/Lillard
share a "type" more than a precise style match), not the automatic failure
0/10 was.

**Other evals**: career continuity recall@10 = 0.54 (vs. a ~0.25% random
baseline for 10 slots out of ~3,975), position predictability accuracy =
0.68 vs. 14.3% chance (7 position classes), cluster stability mean
bootstrap ARI = 0.49. All in `web/public/data/style/style_evals.json`.

**v1 simplification, not yet done**: fit once on the full history rather
than per-season with nightly `transform()` updates (the spec's "freeze
models, transform new data" nightly-refresh mechanic is a Phase 6 concern,
not needed to ship a first working map). Archetype names are generated
heuristically from each cluster's top 2 distinguishing features
(`hub.style.export.name_archetype`), not LLM-proposed as the spec suggests —
a reasonable stand-in, but PLAN.md says "edit by hand," so treat the current
names as a first draft. The comp-sanity list is 10 hand-picked pairs, not
the spec's ~30.

## 2026-09-17 — Phase 2: SynergyPlayTypes result-set key is singular, and needs an explicit type_grouping

Two undocumented quirks found live while building the style-map's play-type
features: (1) `SynergyPlayTypes(play_type_nullable=..., type_grouping_nullable=None)`
(the default) returns **zero rows** for every player — must pass
`type_grouping_nullable="offensive"` explicitly. (2) The normalized result-set
key is `"SynergyPlayType"` (singular), not `"SynergyPlayTypes"` — despite the
endpoint class, and every other endpoint's convention, being named after the
plural. Got this wrong on the first pass (assumed the plural by pattern-matching
other endpoints) and it surfaced immediately as a `KeyError` wrapped in
`FetchError`, burning retry/backoff time on every play-type call before the
per-item skip logic silently swallowed it — a reminder that a `KeyError` from
a code bug looks identical to a real network failure through that retry loop,
so it's worth checking the *type* of a repeated failure before assuming it's
the network. Fixed in `hub.fetch.nba.fetch_synergy_play_type`.

Also confirmed **`LeagueDashPtStats(pt_measure_type="Possessions")`** already
includes touches, seconds/dribbles per touch, and elbow/post/paint touch
counts — no separate "touch location" measure type needed, cutting the
style-map's tracking-data fetch from an estimated 8 measure types down to 5
(`Possessions, Drives, Passing, CatchShoot, PullUpShot`).

## 2026-09-17 — Correction: the "12+ hour stats.nba.com outage" was a bad diagnostic, not a real outage

The original PBP timeout during the Phase 1 backfill was real (an actual
`hub.fetch.client` retry loop, using real `nba_api` requests, genuinely timed
out on one game). But every check *after* that used a hand-rolled `curl`
reproduction with a minimal, obviously-non-browser header set (bare
`User-Agent: Mozilla/5.0`, missing `Sec-Ch-Ua`, `Accept-Encoding: br`,
`Accept-Language`, etc.). Compared `nba_api`'s actual headers
(`nba_api.stats.library.http.STATS_HEADERS`) against that curl command:
`nba_api` sends a full realistic Chrome fingerprint; my curl didn't. That
minimal header set is exactly what bot-mitigation (Akamai, in front of
stats.nba.com) is built to catch — so my curl kept getting silently dropped
regardless of whether the real API was reachable, and every "still down"
conclusion after the first one was built on that flawed test, not on the
actual fetch layer. Confirmed by running the real `nba_api` library directly:
it succeeded in under a second, no different from a normal day.

**Lesson**: don't reproduce a library's HTTP behavior by hand to diagnose
connectivity — use the library itself. A hand-rolled request that looks
"close enough" can fail for reasons entirely unrelated to what's actually
being diagnosed, and every debugging step built on it inherits the error.
The likely real timeline: one genuinely flaky request mid-backfill, probably
recovered within minutes to an hour, not the ~24-hour block described in the
now-corrected entries below.

## 2026-09-17 — Ask the box score: model choice, a real 8B refusal bug, and measured neuron cost

Deployed `/api/ask` live and tested against the real Workers AI catalog
(`npx wrangler ai models list`, ~180 models as of today — far more than
training data would suggest, confirming PLAN.md's warning not to assume the
catalog). No `wrangler ai run` CLI command exists in wrangler 4.132.0 (only
`models` and `finetune` subcommands) — model comparisons had to go through
real deployed requests, not a local CLI shortcut.

**Started with `@cf/meta/llama-3.1-8b-instruct-fp8`** (small, cheap). It
worked for most questions but **reproducibly refused any question mentioning
the 2024-25 or 2025-26 season, regardless of the stat asked** ("Who had the
most points/assists/rebounds in the 2024-25 season?" all refused; the same
questions for 2019-20 or 2023-24 worked fine). This held even after
explicitly telling the model in the system prompt that it's translating to
SQL against a real, already-loaded schema, not recalling facts, and that it
should never refuse based on the season alone — the small model's own
training-cutoff caution overrode the instruction. `@cf/meta/llama-3.2-3b-instruct`
(the original fallback) would presumably have the same issue, untested.

**Switched primary to `@cf/meta/llama-3.3-70b-instruct-fp8-fast`**, which
handles the same recent-season questions correctly with clean SQL. Kept the
8B and 3B models as fallbacks in `MODEL_FALLBACKS` (`worker/src/ask.ts`) for
resilience if the 70B model is ever retired or rate-limited — but note this
is imperfect: a spurious refusal is a valid (non-error) response, so it
won't trigger the fallback list's error-based fallthrough. If Workers AI
ever routes to the 8B/3B fallback, recent-season questions will start
getting wrongly refused rather than the whole feature breaking — degraded,
not broken, which fits PLAN.md's "fail open" philosophy but is worth knowing.

**Measured live** (via `wrangler tail`, real requests): **34.1 neurons per
question** on the 70B model (vs. 11.86 on the 8B model — about 3x). Against
the 10,000 neurons/day free allocation, that's **~290 questions/day** of
headroom. Set `DAILY_QUESTION_BUDGET = 250` in code accordingly (leaves
~1,475 neurons of slack per day for repair-attempt retries).

**Still open**: this is based on manual spot checks, not the full golden-set
execution-accuracy comparison PLAN.md asks for (`evals/ask/golden.jsonl`,
~60 questions, not yet written). Do that before treating 70B as final —
it may turn out a mid-size model handles recent seasons fine with a
different prompt structure, which would be cheaper.

## 2026-09-17 — DuckDB-WASM: relative registered-file URLs resolve against the wrong origin

**Issue.** `db.registerFileURL(name, url, DuckDBDataProtocol.HTTP, false)` with
a relative `url` (e.g. `/data/ask/players.parquet`) failed at query time with
`SyntaxError: Failed to execute 'open' on 'XMLHttpRequest': Invalid URL`. Root
cause: the actual HTTP fetch for a registered file happens inside the
DuckDB-WASM worker script, which — per PLAN.md's own design — is loaded from
jsDelivr, not our own origin. A relative URL registered from the main thread
resolves against *the worker's* location when the fetch actually happens, so
it was resolving against jsDelivr, not our site. Fixed by registering an
absolute URL (`${window.location.origin}/data/ask/${file}`) in
`web/lib/duckdb.ts`.

**Also found**: `read_parquet([...])` (the array/multi-file form) doesn't
correctly resolve HTTP-registered virtual files the same way the single-
argument `read_parquet('name')` does — same "Invalid URL" failure even with
an absolute registered URL. Worked around by using plain `read_parquet('name')`
per file and `UNION ALL`-ing them for `player_game_logs` (sharded one file per
season) instead of passing an array.

Both verified live with Playwright driving a real browser against the dev
server, not assumed from the API surface.

## 2026-09-17 — Phase 1 complete: data quality report and known gaps

Built the full canonical tables from the 2015-16 → 2025-26 backfill. 13/15
quality checks pass. Row counts: `teams` 30, `players` 5,217 (bios for the
1,554 who appear 2015-16+), `games` 13,199, `player_game_logs` 281,164,
`team_game_logs` 26,418, `player_seasons` 5,968, `shots` 2,319,756,
`pbp_events` 1,086,360 (partial — see below).

**Known gap 1: `games` is short exactly 5 games each in 2024-25 and 2025-26
only** (1,225 vs. the expected 1,230; every other season, including the
COVID-shortened 2019-20/2020-21, has its correct count). The missing games
*do* have real shot and play-by-play data — they're just absent from
`LeagueGameLog`'s "Regular Season" pull specifically. Most likely explanation:
NBA Cup (in-season tournament) knockout-round games, which started counting
toward team/player stats in ways that don't always land in the standard
season game log the same way group-stage games do. This causes the two
failed quality checks (`shots`→`games` and `pbp_events`→`games` join
integrity, 10 and 2 orphaned game_ids respectively — a ~0.08% gap). Low
priority: doesn't affect Phase 2 or 3 at all, and is small enough that Phase
4/5 can special-case or simply drop these games when the time comes. Revisit
by fetching those 12 specific game_ids' info directly if it matters later.

**Known gap 2: `pbp_events` covers only 2023-24 and 2024-25, not 2025-26.**
`stats.nba.com` started silently dropping connections (TLS handshake
succeeds, zero bytes returned, every request) partway through the backfill —
most likely Akamai-level bot mitigation triggered by the sustained ~2 hours
of automated requests, not a genuine site outage (confirmed: general internet
access unaffected, and the outage persisted for 12+ hours, which is far
longer than the earlier single-game timeouts). Since play-by-play is Phase
5's data (game flow), not Phase 2/3's, shipped Phase 1 with what's cached
rather than block on it. Added `--pbp-cache-only` to `hub.tables.pipeline`
for this: builds every table from cache with zero network calls, skipping
(and recording in `quality_report.json`'s `skipped` key) any play-by-play
game not already fetched. Resume the rest with `make tables` (without the
flag) once `stats.nba.com` is reachable again — everything else is already
complete so it'll only spend time on the remaining ~1,470 games.

## 2026-09-16 — Phase 1 backfill: one flaky game crashed the whole multi-hour run

**Issue.** ~50 minutes into the full 2015-16→2025-26 backfill, `PlayByPlayV3`
for one game (`0022300093`) hit a 30s read timeout 5 times in a row (retries
exhausted, ~4 minutes of backoff), and `FetchError` propagated all the way up
and crashed the process. Everything already fetched was safely cached to disk
(cache writes happen per-call, immediately), so no API calls were wasted — but
the in-memory canonical tables (built once at the very end) were never written
to Parquet, so the run had to restart from where table-building begins, even
though 99%+ of the fetching was already done and cached.

**Fix.** In both `hub.fetch.backfill` and `hub.tables.pipeline`, the
per-team shot fetches, per-player bio fetches, and per-game play-by-play
fetches now catch `FetchError` individually, log a warning, and continue the
loop instead of propagating. `hub.tables.pipeline` also records every skipped
item in the final `quality_report.json` under a `skipped` key (by season/team,
player_id, or season/game_id) so gaps are visible and re-fetchable later,
rather than silently missing. Season-level calls (game logs, season stats)
still fail loudly and stop the run — losing an entire season's box scores
means something is systemically wrong, not "one flaky request," so that
shouldn't be swallowed the same way.

## 2026-09-16 — Phase 1: nba_api endpoint corrections (verified live)

PLAN.md flagged these as "confirm before writing code." Endpoint names,
parameters, and enum values below were checked against nba_api 1.11.4's
source (`nba_api/stats/library/parameters.py`, endpoint `__init__` signatures)
and against live responses from stats.nba.com — not assumed.

**`ShotChartDetail` league-wide truncates at exactly 102,400 rows.** Querying
`team_id=0, player_id=0` for a full season (2023-24) returned 102,400 rows
covering only 575 of ~1,230 games (through mid-January) — a hard API cap, not
a nba_api bug. Must query per team instead (`team_id=<real id>, player_id=0`),
which returns complete, untruncated season data (verified: 82/82 games for one
team). This means 30 calls/season for shots, not 1 — PLAN.md's estimate table
already listed "1–30" anticipating this; 30 is the confirmed answer.

**`PlayerIndex` is not season-scoped despite taking a `season` param.**
`PlayerIndex(season="2023-24")` returned 141 rows — the *current* roster count
at call time — versus 572 unique players who actually logged a game in
2023-24 per `LeagueGameLog`. It's a current-roster endpoint, not a historical
per-season one. Switched to per-player `CommonPlayerInfo(player_id=...)`
instead, which has complete bio fields (height, weight, position, birthdate,
draft, school) for any player, at the cost of one call per player. Scoped to
only the player_ids that actually appear in `player_game_logs` for our
2015-16+ window (not nba_api's full ~5,200-player all-time roster), which
bounds it to roughly 600–1,000 calls total, not per season.

**`PlayByPlayV3`'s `get_normalized_dict()` returns nothing.** Its response
shape isn't the classic `resultSets` format nba_api's normalizer expects
(confirmed by reading `nba_api/stats/endpoints/playbyplayv3.py`:
`load_response()` builds `.play_by_play` from `nba_response.get_data_sets()`,
a different code path). Caching `.play_by_play.get_dict()` directly instead —
a `{"headers": [...], "data": [[...], ...]}` shape — works and is what
`hub.fetch.nba.fetch_play_by_play` does. Its columns are also camelCase
(`gameId`, `actionNumber`, ...), unlike every other endpoint's `UPPER_SNAKE`,
and `clock` is an ISO-8601 duration string (`"PT12M00.00S"`), not seconds —
both renamed/left for Phase 5's play-by-play parser to handle.

**`LeagueGameLog` and `LeagueDashPlayerStats` behave as documented.** One call
per season per mode (player/team) returns the complete season already — no
pagination surprises there.

## 2026-09-16 — pytest reads `pipeline/src` via `pythonpath`, not the editable install

**Issue.** `uv sync` installs `hub` as editable via a `.pth` file pointing at
`pipeline/src`. The repo lives under `~/Desktop`, which iCloud Drive syncs;
iCloud sets the macOS `UF_HIDDEN` flag on files it's managing, including that
`.pth` file, at unpredictable times. Python 3.13's `site.py` skips hidden
`.pth` files (a deliberate security fix, since 3.12.3), so `import hub` fails
intermittently with `ModuleNotFoundError` depending on iCloud's sync state —
with no code change and no error at `uv sync` time.

**Fix.** Added `pythonpath = ["src"]` to `[tool.pytest.ini_options]` in
`pipeline/pyproject.toml`. This is pytest's built-in mechanism (no plugin) for
inserting a path into `sys.path` directly, independent of `site.py`'s `.pth`
processing, so tests are immune to the hidden-flag state.

**Update (same day):** this hit for real during the Phase 1 backfill —
`uv run python -m hub.tables.pipeline` failed twice in a row with
`ModuleNotFoundError: No module named 'hub'`, seconds apart, even right after
manually clearing the hidden flag each time. iCloud's sync daemon is
re-hiding the file on its own schedule, independent of `uv`/`chflags` — a
one-off `chflags nohidden` is a losing race for an unattended multi-hour job.

**Permanent fix:** `PYTHONPATH=src` set directly on the command (now baked
into the `fetch` and `tables` Makefile targets), not `chflags`. `PYTHONPATH`
is read by the interpreter at startup and doesn't go through `site.py`'s
`.pth` processing at all, so it's unaffected by the hidden flag regardless of
iCloud's timing. The `chflags nohidden` one-liner below still works as a
one-off if `hub` is ever imported directly without `PYTHONPATH=src` set:

```
chflags nohidden pipeline/.venv/lib/python3.13/site-packages/_editable_impl_hub.pth
```

The most permanent fix is keeping the repo outside an iCloud-synced folder
(or excluding it from iCloud), which is Svej's call, not something to change
unilaterally — but with `PYTHONPATH=src` in place this no longer blocks work.

## 2026-09-16 — Phase 0 scaffold: stack versions

Recorded the exact versions installed during scaffolding, since PLAN.md notes
these move fast and should be reverified before relying on them:

- Python 3.13.1, `uv` 0.12.15
- Node v23.4.0, `pnpm` 12.4.2 (installed via Homebrew; Node's built-in
  `corepack prepare pnpm@latest` failed with a signature-verification error
  on this machine — a known corepack/npm registry signing issue, not specific
  to this project)
- Next.js 16.3.5 (App Router), React 19.2.8 — notably newer than this
  model's training data; the static-export config (`output: "export"`) was
  verified against the docs bundled in `node_modules/next/dist/docs/` rather
  than assumed
- Wrangler 4.132.0. The `assets` config in `worker/wrangler.jsonc`
  (`directory`, `binding`, `not_found_handling`, `run_worker_first`) was
  verified against `node_modules/wrangler/config-schema.json` rather than
  assumed, since this is also newer than training data
- `wrangler login` was not run — it needs an interactive browser flow, so
  it's left for Svej to do locally before the first real `wrangler deploy`
