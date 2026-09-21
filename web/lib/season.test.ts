import { describe, expect, it } from "vitest";
import { formatSeason } from "./season";

describe("formatSeason", () => {
  it("formats a standard season", () => {
    expect(formatSeason(2024)).toBe("2024-25");
  });

  it("wraps the century correctly", () => {
    expect(formatSeason(2099)).toBe("2099-00");
  });
});
