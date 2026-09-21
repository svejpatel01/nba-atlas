/**
 * Lazy-loaded DuckDB-WASM for the /ask page. The JS wrapper is a normal
 * dependency (code-split by Next's route-based bundling, so it never touches
 * the landing page bundle), but the multi-MB wasm binary and worker script
 * come from jsDelivr, not our own static assets — see
 * @duckdb/duckdb-wasm's own "CDN (jsdelivr)" instantiation example.
 *
 * Hardening: loads every table as an in-memory Parquet read, then runs
 * `SET enable_external_access=false` (verified against DuckDB 1.5.5 — see
 * docs/decisions.md) so no query afterward can read a file or URL, attach a
 * database, etc. This runs before the SQL guard ever sees a query, as a
 * second, engine-level line of defense.
 */

import * as duckdb from "@duckdb/duckdb-wasm";
import { guardSql } from "../../shared/sql-guard";

export interface AskSchemaManifest {
  schema_version: number;
  tables: Record<
    string,
    {
      file?: string;
      files?: string[];
      rows: number;
      columns: Record<string, string>;
      description: string;
    }
  >;
}

let dbPromise: Promise<duckdb.AsyncDuckDB> | null = null;
let connPromise: Promise<duckdb.AsyncDuckDBConnection> | null = null;

async function instantiateDb(): Promise<duckdb.AsyncDuckDB> {
  const bundles = duckdb.getJsDelivrBundles();
  const bundle = await duckdb.selectBundle(bundles);
  const workerUrl = URL.createObjectURL(
    new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }),
  );
  const worker = new Worker(workerUrl);
  const logger = new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING);
  const db = new duckdb.AsyncDuckDB(logger, worker);
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
  URL.revokeObjectURL(workerUrl);
  return db;
}

async function loadTables(db: duckdb.AsyncDuckDB, conn: duckdb.AsyncDuckDBConnection): Promise<void> {
  const manifest: AskSchemaManifest = await fetch("/data/ask/schema.json").then((r) => r.json());

  for (const [name, table] of Object.entries(manifest.tables)) {
    const files = table.files ?? (table.file ? [table.file] : []);
    for (const file of files) {
      // Absolute URL: the duckdb-wasm worker script itself is loaded from
      // jsDelivr, so a relative URL registered here would resolve against
      // jsDelivr's origin, not ours, once the fetch actually happens inside
      // that worker.
      await db.registerFileURL(
        file,
        `${window.location.origin}/data/ask/${file}`,
        duckdb.DuckDBDataProtocol.HTTP,
        false,
      );
    }
    if (files.length === 1) {
      await conn.query(`CREATE TABLE ${name} AS SELECT * FROM read_parquet('${files[0]}')`);
    } else {
      const unionSql = files.map((f) => `SELECT * FROM read_parquet('${f}')`).join(" UNION ALL ");
      await conn.query(`CREATE TABLE ${name} AS ${unionSql}`);
    }
  }
}

/** Instantiates DuckDB-WASM (once), loads every ask table, and locks down
 * external access. Safe to call multiple times — subsequent calls reuse the
 * same instance.
 */
export async function getAskConnection(): Promise<duckdb.AsyncDuckDBConnection> {
  if (!dbPromise) {
    dbPromise = instantiateDb();
  }
  if (!connPromise) {
    connPromise = (async () => {
      const db = await dbPromise!;
      const conn = await db.connect();
      await loadTables(db, conn);
      await conn.query("SET enable_external_access=false;");
      return conn;
    })();
  }
  return connPromise;
}

export interface AskQueryResult {
  columns: string[];
  rows: Record<string, unknown>[];
}

/** Runs a query through the shared SQL guard, then executes it. Throws if
 * the guard rejects the query — callers should catch and show the reason.
 */
export async function runGuardedQuery(sql: string): Promise<AskQueryResult> {
  const guarded = guardSql(sql);
  if (!guarded.ok) {
    throw new Error(guarded.reason ?? "Query rejected.");
  }
  const conn = await getAskConnection();
  const table = await conn.query(guarded.sql!);
  const rows = table.toArray().map((row) => row.toJSON() as Record<string, unknown>);
  return { columns: table.schema.fields.map((f) => f.name), rows };
}
