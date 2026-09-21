import { type AskEnv, handleAsk } from "./ask";

export interface Env extends AskEnv {
  ASSETS: Fetcher;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/api/health") {
      return Response.json({ status: "ok", time: new Date().toISOString() });
    }

    if (url.pathname === "/api/ask" && request.method === "POST") {
      try {
        return await handleAsk(request, env);
      } catch (err) {
        // Fail open: the static site (including the zero-cost example
        // gallery) must keep working even if /api/ask breaks.
        console.error("ask handler error", err);
        return Response.json(
          { error: "Ask is temporarily unavailable. Try one of the example questions instead." },
          { status: 503 },
        );
      }
    }

    if (url.pathname.startsWith("/api/")) {
      return Response.json({ error: "not found" }, { status: 404 });
    }

    return env.ASSETS.fetch(request);
  },
} satisfies ExportedHandler<Env>;
