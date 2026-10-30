<!-- Owner: Dev D -->
# frontend

React + Vite + TypeScript + Tailwind v4 app for the APAAR Integrity Platform. Deployed on Vercel (`vercel.json` rewrites every path to `/` for client-side routing).

```sh
npm install
npm run dev        # http://localhost:5173, backend expected at VITE_API_URL (default http://localhost:8000)
npm run build
npm run lint
npm run gen:api    # regenerate src/lib/api-types.ts from ../shared/openapi.json
```

Create `frontend/.env` yourself from the frontend block of `../.env.example`. Without Supabase variables, `src/lib/supabase.ts` exports `null` and the app runs against the mock API.

| Path | Purpose | Owner |
| --- | --- | --- |
| `src/lib/api.ts` | `api<T>()` fetch wrapper; sends `X-Demo-Role` and `X-Demo-Institution`; tracks `X-Mock` | Dev D |
| `src/lib/roles.ts` | Demo role store (localStorage) | Dev D |
| `src/lib/supabase.ts` | Supabase client or `null` | Dev D |
| `src/components/` | Layout (header, MOCK badge, role switcher, nav), shared components | Dev D |
| `src/pages/institution/`, `aicte/`, `blindmatch/` | Institution, AICTE and Blind Match screens | Dev D |
| `src/pages/student/`, `verifier/` | Student and verifier screens | Dev E |

Each page currently fetches one mock endpoint and prints the JSON, so every owner starts from a working data path.

**Known issue:** `openapi-typescript` (latest 7.13.0) declares `typescript@^5.x` as a peer, and this template uses TypeScript 6, so `npm install -D openapi-typescript` fails with ERESOLVE. `gen:api` does not run until that is fixed (see the setup handoff for options). Pages use small local interfaces marked `TODO` until then.
