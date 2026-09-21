# web

Next.js static export for the NBA data hub. Ships as static assets served by
the Cloudflare Worker in `../worker/`; there is no Node server at runtime.

```bash
pnpm dev       # local dev server
pnpm build     # static export to out/
pnpm test      # vitest
pnpm lint      # eslint
pnpm typecheck # tsc --noEmit
```

See `../README.md` and `../PLAN.md` for the full project.
