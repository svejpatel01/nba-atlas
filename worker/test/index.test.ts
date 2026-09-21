import { describe, expect, it } from "vitest";
import worker, { type Env } from "../src/index";

function makeEnv(): Env {
  return {
    ASSETS: {
      fetch: async () => new Response("asset", { status: 200 }),
    } as unknown as Fetcher,
    AI: { run: async () => ({ response: "REFUSE" }) } as unknown as Ai,
    ASK_KV: {
      get: async () => null,
      put: async () => undefined,
    } as unknown as KVNamespace,
    ASK_RATE_LIMIT: { limit: async () => ({ success: true }) } as unknown as RateLimit,
  };
}

describe("worker fetch handler", () => {
  it("responds ok on /api/health", async () => {
    const res = await worker.fetch(new Request("https://example.com/api/health"), makeEnv());
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({ status: "ok" });
  });

  it("404s on unknown /api/* routes", async () => {
    const res = await worker.fetch(new Request("https://example.com/api/nope"), makeEnv());
    expect(res.status).toBe(404);
  });

  it("falls through to ASSETS for non-api routes", async () => {
    const res = await worker.fetch(new Request("https://example.com/style-map"), makeEnv());
    expect(await res.text()).toBe("asset");
  });
});
