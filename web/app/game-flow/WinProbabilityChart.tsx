"use client";

import { useMemo, useState } from "react";
import {
  formatGameClock,
  quarterBoundaries,
  type GameBundle,
} from "../../lib/gameflow";
import styles from "./game-flow.module.css";

const WIDTH = 720;
const HEIGHT = 320;
const PADDING = { top: 16, right: 16, bottom: 28, left: 40 };

interface Props {
  bundle: GameBundle;
  homeTeam: string;
  awayTeam: string;
}

interface HoverState {
  x: number;
  secondsElapsed: number;
  homeWinProb: number;
  homeScore: number;
  awayScore: number;
}

export default function WinProbabilityChart({ bundle, homeTeam, awayTeam }: Props) {
  const [hover, setHover] = useState<HoverState | null>(null);
  const [pinnedPlay, setPinnedPlay] = useState<number | null>(null);

  const series = bundle.series;
  const maxSeconds = series.length > 0 ? series[series.length - 1][0] : 2880;
  const plotWidth = WIDTH - PADDING.left - PADDING.right;
  const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;

  const xScale = (seconds: number) => PADDING.left + (seconds / maxSeconds) * plotWidth;
  const yScale = (winProb: number) => PADDING.top + (1 - winProb) * plotHeight;

  const pathD = useMemo(() => {
    return series
      .map(([t, wp], i) => `${i === 0 ? "M" : "L"} ${xScale(t).toFixed(1)} ${yScale(wp).toFixed(1)}`)
      .join(" ");
    // xScale/yScale are plain functions recreated every render from
    // plotWidth/plotHeight/maxSeconds — listing them would defeat the memo
    // without changing behavior, since they're stable in every way that
    // matters (maxSeconds is already a dep).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [series, maxSeconds]);

  const boundaries = useMemo(() => quarterBoundaries(maxSeconds), [maxSeconds]);

  function nearestSeriesPoint(seconds: number) {
    let best = series[0];
    let bestDist = Math.abs(series[0][0] - seconds);
    for (const point of series) {
      const dist = Math.abs(point[0] - seconds);
      if (dist < bestDist) {
        best = point;
        bestDist = dist;
      }
    }
    return best;
  }

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const seconds = Math.max(0, Math.min(maxSeconds, ((px - PADDING.left) / plotWidth) * maxSeconds));
    const [t, wp, hs, as] = nearestSeriesPoint(seconds);
    setHover({ x: xScale(t), secondsElapsed: t, homeWinProb: wp, homeScore: hs, awayScore: as });
  }

  const activePlayIdx = pinnedPlay ?? null;

  return (
    <div className={styles.chartWrap}>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className={styles.chartSvg}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* 50% reference line */}
        <line
          x1={PADDING.left}
          x2={WIDTH - PADDING.right}
          y1={yScale(0.5)}
          y2={yScale(0.5)}
          className={styles.refLine}
        />

        {/* quarter boundaries */}
        {boundaries.map((t) => (
          <line
            key={t}
            x1={xScale(t)}
            x2={xScale(t)}
            y1={PADDING.top}
            y2={HEIGHT - PADDING.bottom}
            className={styles.quarterLine}
          />
        ))}

        {/* y-axis labels */}
        <text x={4} y={yScale(1) + 4} className={styles.axisLabel}>
          100%
        </text>
        <text x={4} y={yScale(0.5) + 4} className={styles.axisLabel}>
          50%
        </text>
        <text x={4} y={yScale(0) + 4} className={styles.axisLabel}>
          0%
        </text>

        <path d={pathD} className={styles.wpLine} />

        {/* top-play markers */}
        {bundle.top_plays.map((play, i) => {
          const [t, wp] = nearestSeriesPoint(play.seconds_elapsed);
          return (
            <circle
              key={i}
              cx={xScale(t)}
              cy={yScale(wp)}
              r={5}
              className={styles.playMarker}
              onMouseEnter={() => setPinnedPlay(i)}
              onMouseLeave={() => setPinnedPlay(null)}
            />
          );
        })}

        {hover && (
          <line
            x1={hover.x}
            x2={hover.x}
            y1={PADDING.top}
            y2={HEIGHT - PADDING.bottom}
            className={styles.hoverLine}
          />
        )}
      </svg>

      {hover && activePlayIdx === null && (
        <div className={styles.tooltip}>
          {formatGameClock(hover.secondsElapsed)} — {awayTeam} {hover.awayScore} @ {homeTeam}{" "}
          {hover.homeScore} — {homeTeam} {(hover.homeWinProb * 100).toFixed(0)}% to win
        </div>
      )}

      {activePlayIdx !== null && (
        <div className={styles.tooltip}>
          <strong>{formatGameClock(bundle.top_plays[activePlayIdx].seconds_elapsed)}</strong>{" "}
          {bundle.top_plays[activePlayIdx].description} — {awayTeam}{" "}
          {bundle.top_plays[activePlayIdx].away_score} @ {homeTeam} {bundle.top_plays[activePlayIdx].home_score}{" "}
          ({bundle.top_plays[activePlayIdx].wp_change >= 0 ? "+" : ""}
          {(bundle.top_plays[activePlayIdx].wp_change * 100).toFixed(1)}pp for {homeTeam})
        </div>
      )}
    </div>
  );
}
