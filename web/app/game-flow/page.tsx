"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  formatGameClock,
  loadGameBundle,
  loadGamesIndex,
  type GameBundle,
  type GameIndexEntry,
} from "../../lib/gameflow";
import WinProbabilityChart from "./WinProbabilityChart";
import styles from "./game-flow.module.css";

const SEASONS = ["2023-24", "2024-25", "2025-26"];
const DEFAULT_SEASON = SEASONS[SEASONS.length - 1];

function readUrlParams(): { season: string | null; game: string | null } {
  if (typeof window === "undefined") return { season: null, game: null };
  const params = new URLSearchParams(window.location.search);
  return { season: params.get("season"), game: params.get("game") };
}

function updateUrl(season: string, gameId: string) {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams();
  params.set("season", season);
  params.set("game", gameId);
  window.history.replaceState(null, "", `?${params.toString()}`);
}

export default function GameFlowPage() {
  const [season, setSeason] = useState(DEFAULT_SEASON);
  const [gamesIndex, setGamesIndex] = useState<GameIndexEntry[]>([]);
  const [teamFilter, setTeamFilter] = useState("");
  const [search, setSearch] = useState("");
  const [selectedGame, setSelectedGame] = useState<GameIndexEntry | null>(null);
  const [bundle, setBundle] = useState<GameBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // A game id carried in from a shared URL, consumed once the matching
  // season's index has loaded. A ref (not state) because it's a one-time
  // handoff between effects, not something the UI renders directly.
  const urlGameIdRef = useRef<string | null>(null);

  // Shareable URLs: pick up ?season=&game= on first load.
  useEffect(() => {
    const { season: urlSeason, game: urlGame } = readUrlParams();
    urlGameIdRef.current = urlGame;
    if (urlSeason && SEASONS.includes(urlSeason)) {
      // One-time sync from the URL (an external system) on mount, not a
      // derived/cascading update — the case this lint rule itself calls out
      // as fine ("calling setState in a callback... when external state
      // changes").
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSeason(urlSeason);
    }
  }, []);

  useEffect(() => {
    loadGamesIndex(season)
      .then((data) => {
        setGamesIndex(data);
        setError(null);
        const pendingId = urlGameIdRef.current;
        if (pendingId) {
          urlGameIdRef.current = null;
          const match = data.find((g) => g.game_id === pendingId);
          if (match) selectGame(match, false);
        }
      })
      .catch(() => setError("Failed to load this season's game index."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season]);

  function selectGame(game: GameIndexEntry, writeUrl = true) {
    setSelectedGame(game);
    setBundle(null);
    setLoading(true);
    setError(null);
    if (writeUrl) updateUrl(season, game.game_id);
    loadGameBundle(season, game.date, game.game_id)
      .then((b) => {
        if (!b) {
          setError("Couldn't find this game's play-by-play detail.");
          return;
        }
        setBundle(b);
      })
      .catch(() => setError("Failed to load this game's win-probability data."))
      .finally(() => setLoading(false));
  }

  const teams = useMemo(() => {
    const set = new Set<string>();
    for (const g of gamesIndex) {
      set.add(g.home_team);
      set.add(g.away_team);
    }
    return [...set].sort();
  }, [gamesIndex]);

  const teamFiltered = useMemo(() => {
    if (!teamFilter) return gamesIndex;
    return gamesIndex.filter((g) => g.home_team === teamFilter || g.away_team === teamFilter);
  }, [gamesIndex, teamFilter]);

  const filteredGames = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = q
      ? teamFiltered.filter(
          (g) =>
            g.date.includes(q) ||
            g.home_team.toLowerCase().includes(q) ||
            g.away_team.toLowerCase().includes(q),
        )
      : teamFiltered;
    return [...list].sort((a, b) => (a.date < b.date ? 1 : -1));
  }, [teamFiltered, search]);

  const mostExciting = useMemo(
    () => [...teamFiltered].sort((a, b) => b.excitement - a.excitement).slice(0, 10),
    [teamFiltered],
  );
  const biggestComebacks = useMemo(
    () => [...teamFiltered].sort((a, b) => b.comeback_factor - a.comeback_factor).slice(0, 10),
    [teamFiltered],
  );

  return (
    <main className={styles.page}>
      <div className={styles.header}>
        <h1>Game flow</h1>
        <p>
          Win probability, possession by possession, for every game since 2023-24 — built from
          play-by-play data and an Elo-based pregame model, no betting-line data involved. Pick a
          game below, or start from the season&apos;s most exciting finishes and biggest
          comebacks.
        </p>
      </div>

      <div className={styles.controlBar}>
        <select
          value={season}
          onChange={(e) => {
            setSeason(e.target.value);
            setSelectedGame(null);
            setBundle(null);
            setTeamFilter("");
          }}
          className={styles.select}
        >
          {SEASONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        <select value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)} className={styles.select}>
          <option value="">All teams</option>
          {teams.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>

        <input
          type="text"
          placeholder="Search by team or date…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className={styles.searchInput}
        />
      </div>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.body}>
        <div className={styles.picker}>
          {filteredGames.map((g) => (
            <button
              key={g.game_id}
              type="button"
              className={`${styles.pickerRow} ${selectedGame?.game_id === g.game_id ? styles.pickerRowActive : ""}`}
              onClick={() => selectGame(g)}
            >
              <span className={styles.pickerDate}>{g.date}</span>
              <span className={styles.pickerMatchup}>
                {g.away_team} {g.away_score} @ {g.home_team} {g.home_score}
              </span>
            </button>
          ))}
        </div>

        <div className={styles.mainArea}>
          {!selectedGame && <p className={styles.emptyHint}>Select a game to see how it unfolded.</p>}

          {selectedGame && (
            <>
              <div className={styles.gameHeader}>
                <h2>
                  {selectedGame.away_team} {selectedGame.away_score} @ {selectedGame.home_team}{" "}
                  {selectedGame.home_score}
                </h2>
                <span className={styles.eloLine}>{selectedGame.date}</span>
              </div>

              {bundle && (
                <span className={styles.eloLine}>
                  Pregame Elo — {selectedGame.away_team}: {bundle.pregame_elo.away}, {selectedGame.home_team}:{" "}
                  {bundle.pregame_elo.home}
                </span>
              )}

              {loading && <p className={styles.emptyHint}>Loading…</p>}

              {bundle && !loading && (
                <>
                  <WinProbabilityChart
                    bundle={bundle}
                    homeTeam={selectedGame.home_team}
                    awayTeam={selectedGame.away_team}
                  />
                  <div className={styles.topPlaysList}>
                    <h3>Biggest swings</h3>
                    {bundle.top_plays.map((p, i) => (
                      <div key={i} className={styles.topPlayRow}>
                        <span>
                          {formatGameClock(p.seconds_elapsed)} — {p.description}
                        </span>
                        <span className={styles.metricValue}>
                          {p.wp_change >= 0 ? "+" : ""}
                          {(p.wp_change * 100).toFixed(1)}pp
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      </div>

      <div className={styles.seasonLists}>
        <div className={styles.seasonListCard}>
          <h3>Most exciting games{teamFilter ? ` — ${teamFilter}` : ""}</h3>
          {mostExciting.map((g) => (
            <button
              key={g.game_id}
              type="button"
              className={styles.seasonListRow}
              onClick={() => selectGame(g)}
            >
              <span>
                {g.date} — {g.away_team} {g.away_score} @ {g.home_team} {g.home_score}
              </span>
              <span className={styles.metricValue}>{g.excitement.toFixed(1)}</span>
            </button>
          ))}
        </div>

        <div className={styles.seasonListCard}>
          <h3>Biggest comebacks{teamFilter ? ` — ${teamFilter}` : ""}</h3>
          {biggestComebacks.map((g) => (
            <button
              key={g.game_id}
              type="button"
              className={styles.seasonListRow}
              onClick={() => selectGame(g)}
            >
              <span>
                {g.date} — {g.away_team} {g.away_score} @ {g.home_team} {g.home_score}
              </span>
              <span className={styles.metricValue}>{(g.comeback_factor * 100).toFixed(0)}%</span>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
