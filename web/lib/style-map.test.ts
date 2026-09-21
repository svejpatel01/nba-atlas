import { describe, expect, it } from "vitest";
import { archmax, describeZScore, findNearestNeighbors, type StyleMapPoint } from "./style-map";

function makePoint(overrides: Partial<StyleMapPoint>): StyleMapPoint {
  return {
    player_id: 1,
    name: "Test Player",
    season: "2023-24",
    team_id: 1,
    team: "TST",
    minutes: 2000,
    provisional: false,
    x: 0,
    y: 0,
    vec: [1, 0, 0],
    arch: [0.9, 0.1],
    fingerprint: {},
    panel: { pts_per36: 20, ts_pct: 0.58, height: "6-6", position: "G" },
    ...overrides,
  };
}

describe("archmax", () => {
  it("returns the index of the highest archetype probability", () => {
    expect(archmax(makePoint({ arch: [0.1, 0.7, 0.2] }))).toBe(1);
    expect(archmax(makePoint({ arch: [0.8, 0.1, 0.1] }))).toBe(0);
  });
});

describe("describeZScore", () => {
  it("labels near-zero values as about average", () => {
    expect(describeZScore(0)).toBe("About average");
    expect(describeZScore(0.2)).toBe("About average");
    expect(describeZScore(-0.2)).toBe("About average");
  });

  it("scales the wording with magnitude, in the right direction", () => {
    expect(describeZScore(0.5)).toBe("Somewhat more than average");
    expect(describeZScore(-0.5)).toBe("Somewhat less than average");
    expect(describeZScore(1.0)).toBe("More than average");
    expect(describeZScore(-1.0)).toBe("Less than average");
    expect(describeZScore(2.0)).toBe("Much more than average");
    expect(describeZScore(-2.0)).toBe("Much less than average");
  });

  it("is monotonic in magnitude near the class boundaries", () => {
    // Guards against an off-by-boundary regression silently flattening the scale.
    expect(describeZScore(0.24)).toBe("About average");
    expect(describeZScore(0.26)).not.toBe("About average");
    expect(describeZScore(0.74)).toBe("Somewhat more than average");
    expect(describeZScore(0.76)).toBe("More than average");
    expect(describeZScore(1.49)).toBe("More than average");
    expect(describeZScore(1.51)).toBe("Much more than average");
  });
});

describe("findNearestNeighbors", () => {
  it("ranks points by cosine similarity, excluding the query itself", () => {
    const points = [
      makePoint({ player_id: 1, name: "Query", vec: [1, 0, 0] }),
      makePoint({ player_id: 2, name: "Close", vec: [0.99, 0.1, 0] }),
      makePoint({ player_id: 3, name: "Far", vec: [0, 1, 0] }),
    ];
    const neighbors = findNearestNeighbors(points, 0, { k: 2 });
    expect(neighbors[0].point.name).toBe("Close");
    expect(neighbors.some((n) => n.point.name === "Query")).toBe(false);
  });

  it("excludes the same player's other seasons when hideOwnSeasons is set", () => {
    const points = [
      makePoint({ player_id: 1, season: "2023-24", vec: [1, 0, 0] }),
      makePoint({ player_id: 1, season: "2022-23", vec: [0.99, 0.1, 0] }),
      makePoint({ player_id: 2, season: "2023-24", vec: [0.5, 0.5, 0] }),
    ];
    const neighbors = findNearestNeighbors(points, 0, { k: 2, hideOwnSeasons: true });
    expect(neighbors.every((n) => n.point.player_id !== 1)).toBe(true);
    expect(neighbors[0].point.player_id).toBe(2);
  });

  it("respects the k limit", () => {
    const points = Array.from({ length: 10 }, (_, i) =>
      makePoint({ player_id: i, vec: [1, i * 0.01, 0] }),
    );
    const neighbors = findNearestNeighbors(points, 0, { k: 3 });
    expect(neighbors).toHaveLength(3);
  });
});
