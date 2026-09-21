import { beforeEach, describe, expect, it, vi } from "vitest";
import { ASK_SCHEMA_VERSION, type AskEnv, handleAsk } from "../src/ask";

// The Cache API (`caches.default`) is a Workers runtime global not present
// in vitest's plain Node environment. A minimal in-memory fake is enough to
// unit-test handleAsk's caching branch without pulling in the full
// Workers runtime (@cloudflare/vitest-pool-workers).
class FakeCache {
  private store = new Map<string, Response>();
  async match(req: Request): Promise<Response | undefined> {
    const hit = this.store.get(req.url);
    return hit ? hit.clone() : undefined;
  }
  async put(req: Request, res: Response): Promise<void> {
    this.store.set(req.url, res.clone());
  }
}

beforeEach(() => {
  (globalThis as unknown as { caches: { default: FakeCache } }).caches = {
    default: new FakeCache(),
  };
});

function makeEnv(overrides: Partial<AskEnv> = {}): AskEnv {
  return {
    AI: { run: vi.fn(async () => ({ response: "SELECT * FROM players LIMIT 5" })) } as unknown as Ai,
    ASK_KV: {
      get: vi.fn(async () => null),
      put: vi.fn(async () => undefined),
    } as unknown as KVNamespace,
    ASK_RATE_LIMIT: { limit: vi.fn(async () => ({ success: true })) } as unknown as RateLimit,
    ...overrides,
  };
}

function req(body: unknown): Request {
  return new Request("https://example.com/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json", "cf-connecting-ip": "1.2.3.4" },
    body: JSON.stringify(body),
  });
}

describe("handleAsk: validation", () => {
  it("rejects a missing question", async () => {
    const res = await handleAsk(req({ schema_version: ASK_SCHEMA_VERSION }), makeEnv());
    expect(res.status).toBe(400);
  });

  it("rejects a question over the length limit", async () => {
    const res = await handleAsk(
      req({ question: "x".repeat(301), schema_version: ASK_SCHEMA_VERSION }),
      makeEnv(),
    );
    expect(res.status).toBe(400);
  });

  it("rejects a stale schema_version", async () => {
    const res = await handleAsk(req({ question: "hi", schema_version: 999 }), makeEnv());
    expect(res.status).toBe(409);
  });

  it("rejects invalid JSON", async () => {
    const badReq = new Request("https://example.com/api/ask", {
      method: "POST",
      body: "not json",
    });
    const res = await handleAsk(badReq, makeEnv());
    expect(res.status).toBe(400);
  });
});

describe("handleAsk: rate limiting", () => {
  it("returns 429 when the rate limiter rejects", async () => {
    const env = makeEnv({
      ASK_RATE_LIMIT: { limit: async () => ({ success: false }) } as unknown as RateLimit,
    });
    const res = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(429);
  });

  it("fails open when the rate limiter throws", async () => {
    const env = makeEnv({
      ASK_RATE_LIMIT: {
        limit: async () => {
          throw new Error("unavailable");
        },
      } as unknown as RateLimit,
    });
    const res = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(200);
  });
});

describe("handleAsk: model output handling", () => {
  it("returns guarded SQL on a normal question", async () => {
    const env = makeEnv();
    const res = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(200);
    const data = (await res.json()) as { sql: string };
    expect(data.sql).toContain("LIMIT");
  });

  it("returns a refusal message when the model outputs REFUSE", async () => {
    const env = makeEnv({
      AI: { run: async () => ({ response: "REFUSE" }) } as unknown as Ai,
    });
    const res = await handleAsk(
      req({ question: "What is the weather today?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    const data = (await res.json()) as { error: string };
    expect(data.error).toContain("NBA");
  });

  it("rejects SQL that fails the guard even if the model produced it", async () => {
    const env = makeEnv({
      AI: { run: async () => ({ response: "DROP TABLE players" }) } as unknown as Ai,
    });
    const res = await handleAsk(
      req({ question: "Delete everything", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(422);
  });

  it("strips markdown code fences from the model response", async () => {
    const env = makeEnv({
      AI: {
        run: async () => ({ response: "```sql\nSELECT * FROM teams\n```" }),
      } as unknown as Ai,
    });
    const res = await handleAsk(
      req({ question: "List teams", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(200);
    const data = (await res.json()) as { sql: string };
    expect(data.sql).toContain("SELECT * FROM teams");
  });

  it("falls through to the next model in the fallback list on error", async () => {
    let calls = 0;
    const env = makeEnv({
      AI: {
        run: async () => {
          calls += 1;
          if (calls === 1) throw new Error("model retired");
          return { response: "SELECT * FROM players LIMIT 5" };
        },
      } as unknown as Ai,
    });
    const res = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(200);
    expect(calls).toBe(2);
  });

  it("fails clearly (fail-open message) when every model fails", async () => {
    const env = makeEnv({
      AI: {
        run: async () => {
          throw new Error("all down");
        },
      } as unknown as Ai,
    });
    const res = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(503);
  });
});

describe("handleAsk: caching", () => {
  it("caches an identical question and does not call the model twice", async () => {
    const runSpy = vi.fn(async () => ({ response: "SELECT * FROM players LIMIT 5" }));
    const env = makeEnv({ AI: { run: runSpy } as unknown as Ai });

    const first = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(first.status).toBe(200);

    const second = await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(second.status).toBe(200);
    expect(runSpy).toHaveBeenCalledTimes(1);
  });

  it("treats whitespace/case differences as the same cache key", async () => {
    const runSpy = vi.fn(async () => ({ response: "SELECT * FROM players LIMIT 5" }));
    const env = makeEnv({ AI: { run: runSpy } as unknown as Ai });

    await handleAsk(
      req({ question: "Who scored the most points?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    await handleAsk(
      req({ question: "  WHO SCORED   the most points?  ", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(runSpy).toHaveBeenCalledTimes(1);
  });
});

describe("handleAsk: daily budget", () => {
  it("stops calling the model once the daily count is exhausted", async () => {
    const env = makeEnv({
      ASK_KV: {
        get: async () => "100000",
        put: async () => undefined,
      } as unknown as KVNamespace,
    });
    const res = await handleAsk(
      req({ question: "Who scored the most points ever?", schema_version: ASK_SCHEMA_VERSION }),
      env,
    );
    expect(res.status).toBe(429);
  });
});
