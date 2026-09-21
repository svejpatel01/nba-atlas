import { describe, expect, it } from "vitest";
import { guardSql, MAX_ROW_LIMIT } from "../../shared/sql-guard";

describe("guardSql: happy paths", () => {
  it("allows a simple SELECT and appends LIMIT", () => {
    const result = guardSql("SELECT * FROM players");
    expect(result.ok).toBe(true);
    expect(result.sql).toBe(`SELECT * FROM players LIMIT ${MAX_ROW_LIMIT}`);
  });

  it("allows a WITH (CTE) statement and treats the CTE name as a valid table", () => {
    const result = guardSql(
      "WITH top AS (SELECT player_id, pts FROM player_game_logs) SELECT * FROM top",
    );
    expect(result.ok).toBe(true);
    expect(result.sql).toContain("LIMIT 200");
  });

  it("leaves an existing LIMIT under the cap untouched", () => {
    const result = guardSql("SELECT * FROM players LIMIT 10");
    expect(result.ok).toBe(true);
    expect(result.sql).toBe("SELECT * FROM players LIMIT 10");
  });

  it("caps an existing LIMIT over the max", () => {
    const result = guardSql("SELECT * FROM players LIMIT 5000");
    expect(result.ok).toBe(true);
    expect(result.sql).toBe(`SELECT * FROM players LIMIT ${MAX_ROW_LIMIT}`);
  });

  it("allows joins across known tables", () => {
    const result = guardSql(
      "SELECT p.name, g.pts FROM players p JOIN player_game_logs g ON p.player_id = g.player_id",
    );
    expect(result.ok).toBe(true);
  });

  it("strips a trailing semicolon before appending LIMIT", () => {
    const result = guardSql("SELECT * FROM players;");
    expect(result.ok).toBe(true);
    expect(result.sql).toBe(`SELECT * FROM players LIMIT ${MAX_ROW_LIMIT}`);
  });
});

describe("guardSql: adversarial cases", () => {
  it("rejects multiple statements", () => {
    const result = guardSql("SELECT * FROM players; DROP TABLE players;");
    expect(result.ok).toBe(false);
  });

  it("rejects multiple SELECTs stacked with a semicolon", () => {
    const result = guardSql("SELECT 1; SELECT 2;");
    expect(result.ok).toBe(false);
  });

  it("rejects a statement that isn't SELECT or WITH", () => {
    const result = guardSql("DROP TABLE players");
    expect(result.ok).toBe(false);
  });

  it("rejects keywords hidden inside a block comment splitting the token", () => {
    // Stripping the comment must not silently rejoin "SEL" + "ECT".
    const guarded = guardSql("SEL/*sneaky*/ECT * FROM players");
    expect(guarded.ok).toBe(false);
  });

  it("rejects DROP hidden after a line comment", () => {
    const result = guardSql("SELECT * FROM players; -- \nDROP TABLE players");
    expect(result.ok).toBe(false);
  });

  it("rejects DROP disguised inside a string literal check bypass attempt", () => {
    const result = guardSql("SELECT * FROM players WHERE name = 'x'; DROP TABLE players; --'");
    expect(result.ok).toBe(false);
  });

  it("does not flag banned keywords when they only appear inside a string literal", () => {
    // The literal contains the word "update" but this is a single, safe SELECT.
    const result = guardSql("SELECT * FROM players WHERE college = 'update U'");
    expect(result.ok).toBe(true);
  });

  it("rejects ATTACH", () => {
    expect(guardSql("ATTACH 'evil.db' AS evil").ok).toBe(false);
  });

  it("rejects PRAGMA", () => {
    expect(guardSql("PRAGMA database_list").ok).toBe(false);
  });

  it("rejects read_csv file access", () => {
    expect(guardSql("SELECT * FROM read_csv('/etc/passwd')").ok).toBe(false);
  });

  it("rejects read_parquet file access", () => {
    expect(guardSql("SELECT * FROM read_parquet('/tmp/secret.parquet')").ok).toBe(false);
  });

  it("rejects a URL read via httpfs-style access", () => {
    expect(guardSql("SELECT * FROM 'https://evil.example.com/data.csv'").ok).toBe(false);
  });

  it("rejects an unknown table not in the allowlist", () => {
    expect(guardSql("SELECT * FROM secret_admin_table").ok).toBe(false);
  });

  it("rejects INSERT", () => {
    expect(guardSql("INSERT INTO players VALUES (1)").ok).toBe(false);
  });

  it("rejects CREATE TABLE AS SELECT", () => {
    expect(guardSql("CREATE TABLE evil AS SELECT * FROM players").ok).toBe(false);
  });

  it("rejects empty input", () => {
    expect(guardSql("").ok).toBe(false);
    expect(guardSql("   ").ok).toBe(false);
  });
});
