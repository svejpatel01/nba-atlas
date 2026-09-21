/**
 * Shared SQL guard for "ask the box score". Used by both the Worker (before
 * caching an LLM-generated query) and the browser (before executing it in
 * DuckDB-WASM) — both must agree a query is safe before it ever runs.
 *
 * This is intentionally not a full SQL parser: DuckDB-WASM has no
 * server-side process to sandbox, so the guard is the only thing standing
 * between an LLM output (or a crafted question) and arbitrary SQL. It works
 * by stripping strings/comments, then checking the remainder against an
 * allowlist (single SELECT/WITH, known tables only) and a denylist
 * (statement keywords, file/URL-reading functions), and always enforces a
 * row limit.
 */

export const ALLOWED_TABLES = [
  "players",
  "teams",
  "games",
  "player_game_logs",
  "team_game_logs",
  "player_seasons",
] as const;

export const MAX_ROW_LIMIT = 200;

const DENYLISTED_KEYWORDS = [
  "ATTACH",
  "DETACH",
  "COPY",
  "INSTALL",
  "LOAD",
  "PRAGMA",
  "SET",
  "EXPORT",
  "IMPORT",
  "CREATE",
  "INSERT",
  "UPDATE",
  "DELETE",
  "DROP",
  "ALTER",
  "GRANT",
  "REVOKE",
  "CALL",
  "VACUUM",
  "CHECKPOINT",
  "EXECUTE",
  "PREPARE",
];

// Table functions and URL schemes that read outside the tables we loaded.
const DENYLISTED_PATTERNS: RegExp[] = [
  /\bread_csv(_auto)?\s*\(/i,
  /\bread_parquet\s*\(/i,
  /\bread_json(_auto)?\s*\(/i,
  /\bparquet_scan\s*\(/i,
  /\bcsv_scan\s*\(/i,
  /\bglob\s*\(/i,
  /\bhttpfs\b/i,
  /['"]?\b(?:https?|s3|gcs|azure|ftp):\/\//i,
];

export interface GuardResult {
  ok: boolean;
  /** The query with a LIMIT clause enforced, if ok. Otherwise undefined. */
  sql?: string;
  reason?: string;
}

/** Removes string literals, quoted identifiers, and comments, replacing each
 * with a single space so word boundaries and statement structure survive
 * (e.g. `SEL/*x*&#47;ECT` doesn't collapse back into `SELECT`). */
function stripLiteralsAndComments(sql: string): string {
  let out = "";
  let i = 0;
  while (i < sql.length) {
    const two = sql.slice(i, i + 2);
    if (two === "--") {
      const end = sql.indexOf("\n", i);
      i = end === -1 ? sql.length : end;
      out += " ";
      continue;
    }
    if (two === "/*") {
      const end = sql.indexOf("*/", i + 2);
      i = end === -1 ? sql.length : end + 2;
      out += " ";
      continue;
    }
    const ch = sql[i];
    if (ch === "'" || ch === '"') {
      let j = i + 1;
      while (j < sql.length) {
        if (sql[j] === ch && sql[j + 1] === ch) {
          j += 2; // escaped quote
          continue;
        }
        if (sql[j] === ch) {
          j += 1;
          break;
        }
        j += 1;
      }
      i = j;
      out += " ";
      continue;
    }
    out += ch;
    i += 1;
  }
  return out;
}

function splitStatements(strippedSql: string): string[] {
  return strippedSql
    .split(";")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

function extractCteNames(strippedSql: string): Set<string> {
  const names = new Set<string>();
  const re = /\b([a-zA-Z_][a-zA-Z0-9_]*)\s+AS\s*\(/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(strippedSql)) !== null) {
    names.add(m[1].toLowerCase());
  }
  return names;
}

function extractTableReferences(strippedSql: string): string[] {
  const refs: string[] = [];
  const re = /\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)/gi;
  let m: RegExpExecArray | null;
  while ((m = re.exec(strippedSql)) !== null) {
    refs.push(m[1].toLowerCase());
  }
  return refs;
}

function hasExistingLimit(strippedSql: string): number | null {
  const m = strippedSql.match(/\bLIMIT\s+(\d+)\s*$/i);
  return m ? Number.parseInt(m[1], 10) : null;
}

/** Validates a single SQL query and returns it with a row limit enforced.
 * Call this identically on the Worker (before caching) and in the browser
 * (before executing) — both must pass for a query to ever run.
 */
export function guardSql(rawSql: string): GuardResult {
  const sql = rawSql.trim();
  if (sql.length === 0) {
    return { ok: false, reason: "Empty query." };
  }

  const stripped = stripLiteralsAndComments(sql);
  const statements = splitStatements(stripped);

  if (statements.length === 0) {
    return { ok: false, reason: "Empty query." };
  }
  if (statements.length > 1) {
    return { ok: false, reason: "Only a single statement is allowed." };
  }

  const statement = statements[0];
  const leading = statement.trimStart();
  if (!/^(SELECT|WITH)\b/i.test(leading)) {
    return { ok: false, reason: "Only SELECT or WITH statements are allowed." };
  }

  for (const keyword of DENYLISTED_KEYWORDS) {
    const re = new RegExp(`\\b${keyword}\\b`, "i");
    if (re.test(statement)) {
      return { ok: false, reason: `Disallowed keyword: ${keyword}.` };
    }
  }

  // Checked against the raw (unstripped) statement, not the comment/string-
  // stripped version: a quoted URL or path (e.g. FROM 'https://...') is
  // DuckDB table-reference syntax, not an inert string literal, so stripping
  // it first would let it slip through disguised as "just a string."
  for (const pattern of DENYLISTED_PATTERNS) {
    if (pattern.test(sql)) {
      return { ok: false, reason: "Disallowed file or network access in query." };
    }
  }

  const cteNames = extractCteNames(stripped);
  const tableRefs = extractTableReferences(stripped);
  const allowed = new Set<string>(ALLOWED_TABLES);
  for (const ref of tableRefs) {
    if (!allowed.has(ref) && !cteNames.has(ref)) {
      return { ok: false, reason: `Unknown table: ${ref}.` };
    }
  }

  const existingLimit = hasExistingLimit(stripped);
  let finalSql = sql.replace(/;\s*$/, "");
  if (existingLimit === null) {
    finalSql = `${finalSql} LIMIT ${MAX_ROW_LIMIT}`;
  } else if (existingLimit > MAX_ROW_LIMIT) {
    finalSql = finalSql.replace(/\bLIMIT\s+\d+\s*$/i, `LIMIT ${MAX_ROW_LIMIT}`);
  }

  return { ok: true, sql: finalSql };
}
