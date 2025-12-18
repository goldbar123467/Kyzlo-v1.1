# OTQ Bot Dashboard (Space-Themed, Netlify)

Next.js app that reads `reports/state.json` (or a GitHub raw URL) and renders bot metrics with a cosmos glassmorphism UI.

## Run locally
```bash
cd dashboard
npm install
npm run dev
```

Data modes (via `STATE_MODE`):
- `local` (default): reads `../reports/state.json` (set `LOCAL_STATE_PATH` to override)
- `mock`: uses `fixtures/state.sample.json`
- `remote`: fetches `STATE_REMOTE_URL`/`NEXT_PUBLIC_STATE_URL`

Auth
- Password gate via middleware and `/login`.
- Set env `DASH_PASSWORD_HASH` to `sha256(your_password)`; no default is bundled.

## Netlify deploy
- `netlify.toml` already set: build `npm run build`, publish `.next`, functions in `netlify/functions`.
- Env vars to set in Netlify:
  - `STATE_MODE=remote`
  - `REPO_RAW_URL` (e.g., `https://raw.githubusercontent.com/<org>/<repo>/main/reports/state.json`)
  - `GITHUB_TOKEN` (if private repo; not needed for public)
  - `DASH_PASSWORD_HASH` (sha256 of your password)
  - Optional overrides: `STATE_REMOTE_URL`, `LOCAL_STATE_PATH`, `STATE_FIXTURE_PATH`
- Local dev with `netlify dev` will default to `STATE_MODE=local`.

## ISR / caching
- Page exports `revalidate = 300` (5 min) and the API route sets `cache-control: no-store`. Adjust as needed.

## Smoke tests
```bash
npm run test        # vitest
```
- `api/health` handler returns 200.
- `state` schema validates fixture.
- Components render with fixture data.

## Theme toggle
- “Cosmic effects” toggle in the header enables/disables animated backdrop/rocket if you want a calmer view.
This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
