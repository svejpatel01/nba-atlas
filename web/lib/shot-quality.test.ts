import { describe, expect, it } from "vitest";
import {
  classifyShotValue,
  gridCellIndex,
  hexCenter,
  hexId,
  lookupGridXfg,
  type GridMeta,
} from "./shot-quality";

// Reference values generated live from the actual Python implementation
// (hub.shots.hex, hub.shots.grid) — not hand-derived — so this is a real
// parity test between the two languages, matching the pattern PLAN.md asks
// for elsewhere (game-flow's win-probability parity test).
describe("hexId: parity with hub.shots.hex", () => {
  it("matches Python's hex_id for several real points", () => {
    expect(hexId(12.0, 18.0)).toBe("4_3");
    expect(hexId(0.0, 0.0)).toBe("0_0");
    expect(hexId(-10.0, 25.0)).toBe("-3_9");
  });
});

describe("hexCenter: parity with hub.shots.hex", () => {
  it("matches Python's hex_center", () => {
    const [x, y] = hexCenter("3_-1");
    expect(x).toBeCloseTo(9.0, 6);
    expect(y).toBeCloseTo(1.7320508075688776, 6);
  });
});

describe("classifyShotValue: parity with hub.shots.grid", () => {
  it("matches Python's classify_shot_value for corner and arc cases", () => {
    expect(classifyShotValue(23.0, 5.0)).toBe(3); // corner
    expect(classifyShotValue(0.0, 25.0)).toBe(3); // beyond arc
    expect(classifyShotValue(0.0, 10.0)).toBe(2); // inside arc
  });
});

describe("gridCellIndex: parity with hub.shots.grid.cell_index", () => {
  const meta: GridMeta = {
    family_order: ["layup"],
    cell_size_ft: 1.0,
    x_min: -25.0,
    x_max: 25.0,
    y_min: 0.0,
    y_max: 47.0,
    n_cells_per_family: 2350,
    grid_context: { period: 2, seconds_left_in_period: 360 },
  };

  it("matches Python's cell_index for real cell centers", () => {
    expect(gridCellIndex(0.0, 0.5, meta)).toBe(25);
    expect(gridCellIndex(-24.5, 0.5, meta)).toBe(0);
  });

  it("returns null outside the grid bounds", () => {
    expect(gridCellIndex(-30, 10, meta)).toBeNull();
    expect(gridCellIndex(10, 50, meta)).toBeNull();
  });
});

describe("lookupGridXfg", () => {
  it("reads the correct byte for a known family/cell combination", () => {
    const meta: GridMeta = {
      family_order: ["layup", "dunk"],
      cell_size_ft: 1.0,
      x_min: -25.0,
      x_max: 25.0,
      y_min: 0.0,
      y_max: 47.0,
      n_cells_per_family: 4,
      grid_context: { period: 2, seconds_left_in_period: 360 },
    };
    // 2 families x 4 cells; "dunk" block starts at index 4.
    const bytes = new Uint8Array([10, 20, 30, 40, 200, 210, 220, 230]);
    // Cell index for (-24.5, 0.5) with a 2-wide, 4-cell grid: col=0, row=0 -> 0.
    expect(lookupGridXfg(bytes, meta, -24.5, 0.5, "layup")).toBeCloseTo(10 / 255, 6);
    expect(lookupGridXfg(bytes, meta, -24.5, 0.5, "dunk")).toBeCloseTo(200 / 255, 6);
  });

  it("returns null for an unknown action family", () => {
    const meta: GridMeta = {
      family_order: ["layup"],
      cell_size_ft: 1.0,
      x_min: -25.0,
      x_max: 25.0,
      y_min: 0.0,
      y_max: 47.0,
      n_cells_per_family: 1,
      grid_context: { period: 2, seconds_left_in_period: 360 },
    };
    expect(lookupGridXfg(new Uint8Array([100]), meta, -24.5, 0.5, "not_a_family")).toBeNull();
  });
});
