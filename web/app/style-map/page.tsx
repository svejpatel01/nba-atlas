"use client";

import { useEffect, useMemo, useState } from "react";
import {
  archmax,
  describeZScore,
  findNearestNeighbors,
  GROUP_LABELS,
  loadStyleMapData,
  type Archetype,
  type StyleMapPoint,
  type StyleModelMeta,
} from "../../lib/style-map";
import StyleMapCanvas from "./StyleMapCanvas";
import styles from "./style-map.module.css";

export default function StyleMapPage() {
  const [points, setPoints] = useState<StyleMapPoint[] | null>(null);
  const [archetypes, setArchetypes] = useState<Archetype[]>([]);
  const [meta, setMeta] = useState<StyleModelMeta | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);
  const [highlightedArchetype, setHighlightedArchetype] = useState<number | null>(null);
  const [hideOwnSeasons, setHideOwnSeasons] = useState(true);

  useEffect(() => {
    loadStyleMapData()
      .then(({ points, archetypes, meta }) => {
        setPoints(points);
        setArchetypes(archetypes);
        setMeta(meta);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load."));
  }, []);

  const searchResults = useMemo(() => {
    if (!points || search.trim().length < 2) return [];
    const q = search.toLowerCase();
    return points
      .map((p, i) => ({ p, i }))
      .filter(({ p }) => p.name.toLowerCase().includes(q))
      .slice(0, 8);
  }, [points, search]);

  const selected = selectedIndex !== null && points ? points[selectedIndex] : null;
  const hovered = hoverIndex !== null && points ? points[hoverIndex] : null;

  const neighbors = useMemo(() => {
    if (!points || selectedIndex === null) return [];
    return findNearestNeighbors(points, selectedIndex, { k: 8, hideOwnSeasons });
  }, [points, selectedIndex, hideOwnSeasons]);

  if (error) {
    return (
      <main className={styles.page}>
        <p className={styles.error}>Couldn&apos;t load the style map: {error}</p>
      </main>
    );
  }

  if (!points) {
    return (
      <main className={styles.page}>
        <p>Loading player style map…</p>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <div className={styles.header}>
        <h1>Player style map</h1>
        <p>
          {points.length.toLocaleString()} player-seasons, 2015-16 through {meta?.data_through}.
          Placed by how they play, not how well.
        </p>
      </div>

      <div className={styles.controlBar}>
        <div className={styles.searchBox}>
          <input
            type="text"
            placeholder="Search a player…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={styles.searchInput}
          />
          {searchResults.length > 0 && (
            <ul className={styles.searchResults}>
              {searchResults.map(({ p, i }) => (
                <li key={`${p.player_id}-${p.season}`}>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedIndex(i);
                      setSearch("");
                    }}
                  >
                    {p.name} <span>{p.season}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className={styles.body}>
        <div className={styles.mapArea}>
          <StyleMapCanvas
            points={points}
            archetypes={archetypes}
            selectedIndex={selectedIndex}
            highlightedArchetype={highlightedArchetype}
            onSelect={setSelectedIndex}
            onHover={setHoverIndex}
          />
          {hovered ? (
            <div className={styles.hoverTooltip}>
              <strong>{hovered.name}</strong> {hovered.season} {hovered.team ?? ""}
            </div>
          ) : (
            <div className={styles.mapCaption}>
              Players who play similarly sit close together — that&apos;s all position on this
              map means. The axes don&apos;t measure anything specific. Color shows each
              player&apos;s closest archetype; click a name below to isolate it.
            </div>
          )}
          <div className={styles.legend}>
            {archetypes.map((a) => (
              <button
                key={a.id}
                type="button"
                className={styles.legendItem}
                style={{
                  opacity: highlightedArchetype === null || highlightedArchetype === a.id ? 1 : 0.4,
                }}
                onClick={() =>
                  setHighlightedArchetype(highlightedArchetype === a.id ? null : a.id)
                }
              >
                <span className={styles.legendSwatch} style={{ background: a.color }} />
                {a.name}
              </button>
            ))}
          </div>
        </div>

        {selected && (
          <aside className={styles.sidePanel}>
            <button type="button" className={styles.closeButton} onClick={() => setSelectedIndex(null)}>
              ×
            </button>
            <h2>{selected.name}</h2>
            <p className={styles.subhead}>
              {selected.season} · {selected.team ?? "—"} · {selected.minutes.toLocaleString()} min
              {selected.provisional && <span className={styles.provisional}> (provisional)</span>}
            </p>

            <div className={styles.archetypeMix}>
              {selected.arch.map((p, i) =>
                p > 0.03 ? (
                  <div
                    key={i}
                    className={styles.archetypeBar}
                    style={{ width: `${p * 100}%`, background: archetypes[i]?.color }}
                    title={`${archetypes[i]?.name}: ${(p * 100).toFixed(0)}%`}
                  />
                ) : null,
              )}
            </div>
            <p className={styles.topArchetype}>{archetypes[archmax(selected)]?.name}</p>
            <p className={styles.archetypeDescription}>{archetypes[archmax(selected)]?.description}</p>

            <h3>Style fingerprint</h3>
            <p className={styles.sectionHint}>
              How {selected.name.split(" ")[0]}&apos;s game compared to a league-average player
              that season. Blue (right) = more than average, red (left) = less.
            </p>
            <div className={styles.fingerprint}>
              {Object.entries(selected.fingerprint).map(([group, z]) => (
                <div key={group} className={styles.fingerprintRow} title={`z-score: ${z.toFixed(2)}`}>
                  <div className={styles.fingerprintHeadline}>
                    <span className={styles.fingerprintLabel}>{GROUP_LABELS[group] ?? group}</span>
                    <span className={styles.fingerprintValue}>{describeZScore(z)}</span>
                  </div>
                  <div className={styles.fingerprintBarTrack}>
                    <div
                      className={styles.fingerprintBar}
                      style={{
                        width: `${Math.min(Math.abs(z) * 25, 50)}%`,
                        marginLeft: z < 0 ? `${50 - Math.min(Math.abs(z) * 25, 50)}%` : "50%",
                        background: z >= 0 ? "var(--accent-cyan)" : "var(--accent-orange)",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            <h3>Panel stats</h3>
            <dl className={styles.panelStats}>
              <dt>Pts/36</dt>
              <dd>{selected.panel.pts_per36 ?? "—"}</dd>
              <dt>TS%</dt>
              <dd>{selected.panel.ts_pct ? `${(selected.panel.ts_pct * 100).toFixed(1)}%` : "—"}</dd>
              <dt>Height</dt>
              <dd>{selected.panel.height ?? "—"}</dd>
              <dt>Position</dt>
              <dd>{selected.panel.position ?? "—"}</dd>
            </dl>

            <h3>
              Plays most like{" "}
              <label className={styles.toggleLabel}>
                <input
                  type="checkbox"
                  checked={hideOwnSeasons}
                  onChange={(e) => setHideOwnSeasons(e.target.checked)}
                />
                hide own seasons
              </label>
            </h3>
            <ul className={styles.compsList}>
              {neighbors.map(({ point, similarity }) => (
                <li key={`${point.player_id}-${point.season}`}>
                  <button type="button" onClick={() => setSelectedIndex(points.indexOf(point))}>
                    {point.name} <span>{point.season}</span>
                    <span className={styles.similarity}>{(similarity * 100).toFixed(0)}%</span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>
        )}
      </div>
    </main>
  );
}
