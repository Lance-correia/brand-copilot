# Phase 0 validation

Validated locally on 2026-10-17 using Python 3.14.4 and Node 24.9.0. Python 3.11+ is declared in the API package metadata.

- PASS: `npm run typecheck` (`tsc --noEmit`).
- PASS: `npm run build` (Vite production build).
- PASS: `cd apps/api && python -c "import app.main"` with the repository virtual environment activated.
- PASS: `python scripts/seed.py`: `ws_lumen`, 19 assets, brand kit, 3 designs. Re-running leaves the fixture workspace unchanged.
- PASS: JSON Schemas themselves, fixture brand kit, 3 designs, and 4 templates validated against JSON Schema 2020-12.
- PASS: `scripts/smoke_stub.sh`: all 21 contracted HTTP method/path pairs. File route returns PNG bytes; asset deletion returns 204. JSON responses match their contracts. Variant jobs return 1, 2, 3, then 4 designs; decomposition returns one. Seeded lint reports palette, logo size, and safe margin violations. Brand assets and uploaded samples return 403 for AI image editing. Invalid designs return 422.
- PASS: Uvicorn starts and Vite starts on localhost:5173. Vite's /api proxy reaches Brand Copilot. Welcome placeholder visibly rendered in Brave.
- PASS: two-page guidelines PDF rendered and visually inspected.
- PASS: `pip check`.

Port 8000 on IPv4 was already occupied by another project (MarketLens). It was left running. This scaffold was started with `cd apps/api && ../../.venv/bin/python -m uvicorn app.main:app --host ::1 --port 8000`, which works with Vite's configured `http://localhost:8000` proxy and the smoke script's default localhost URL. A free IPv4 port 8000 supports the normal contract command.

`python scripts/smoke_models.py` ran with these results:

| Check | Result | Reason |
| --- | --- | --- |
| DeepSeek-V4-Pro schema-valid JSON | FAIL | AZURE_DEEPSEEK_ENDPOINT, AZURE_DEEPSEEK_API_KEY and deployment name are unset. |
| DeepSeek-V4.1-Flash image + tool call | FAIL | Azure configuration and deployment name are unset. |
| Fast image model, 1024 x 1024 | FAIL | OPENAI_API_KEY is unset. |
| Edit model on generated image | FAIL | Fast generation produced no image; no replacement brand pixels were submitted. |

These failures are configuration/dependency failures before provider requests; provider availability is unverified. Fill the repo-root `.env` using `.env.example`, then rerun. Smoke checks call real clients even when USE_STUBS=1.

Image wrappers follow the official OpenAI Python [generation](https://developers.openai.com/api/reference/python/resources/images/methods/generate) and [editing](https://developers.openai.com/api/reference/python/resources/images/methods/edit) interfaces. Model deployment names and image model identifiers remain configurable in `.env` exactly as contracted.
