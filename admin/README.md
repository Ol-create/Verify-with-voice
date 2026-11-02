# TrueVoice Admin

The admin dashboard for TrueVoice staff: sign in, then onboard and manage the companies that use the API.
Next.js (App Router) + TypeScript + Tailwind + shadcn/ui.

## How it talks to the API

The browser never calls the TrueVoice API and never sees the admin token:

- Signing in runs a Server Action that calls `POST /admin/auth/login` and stores the token in an
  **httpOnly, SameSite=Strict cookie** (Secure in production). Page scripts can't read it.
- Pages are Server Components that call the API from the server through `src/lib/api.ts`
  (`apiFetch`), which adds the token. A rejected token sends the admin back to `/login`.
- `src/middleware.ts` redirects any request without the cookie to `/login`.
- `TRUEVOICE_API_URL` is a server-only variable, and the API needs no CORS for this app.

## Run locally

Requires Node 20+ and the TrueVoice API running (see `../README.md`), with an admin created via
`python -m scripts.create_admin --email you@example.com`.

```bash
cp .env.example .env.local      # PowerShell: Copy-Item .env.example .env.local
npm install
npm run dev                     # http://localhost:3000
```

## Checks

```bash
npm run lint
npm run typecheck
npm run build
```

## Layout

```
src/
  middleware.ts           redirect to /login without a session cookie
  lib/api.ts              server-only API client (apiFetch, ApiError)
  lib/types.ts            API response types
  app/login/              sign-in page, login/logout Server Actions
  app/(dashboard)/        signed-in pages: layout with header, dashboard home
  components/ui/          shadcn/ui components (add more with: npx shadcn@4.22.2 add <name>)
```

## Deploying

Next.js needs a server here (Server Actions, middleware), so a static bucket isn't enough. Deploy to
AWS Amplify Hosting or Vercel and set `TRUEVOICE_API_URL` to the API's HTTPS address as a server
environment variable.
