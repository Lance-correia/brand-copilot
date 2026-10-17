# Phase 0 validation — latest rerun

Validated locally on 2026-10-17 using Python 3.14.4 and Node 24.9.0. Python 3.11+ is declared in the API package metadata.

- PASS: `npm run typecheck` (`tsc --noEmit`).
- PASS: `npm run build` (Vite production build).
- PASS: `cd apps/api && python -c "import app.main"` with the repository virtual environment activated.
- PASS: `python scripts/seed.py`: `ws_lumen`, 19 assets, brand kit, 3 designs. Re-running leaves the fixture workspace unchanged.
- PASS: JSON Schemas themselves, fixture brand kit, 3 designs, and 4 templates validated against JSON Schema 2020-12.
- PASS: `scripts/smoke_stub.sh`: all 21 contracted HTTP method/path pairs. File route returns PNG bytes; asset deletion returns 204. JSON responses match their contracts. Variant jobs return 1, 2, 3, then 4 designs; decomposition returns one. Seeded lint reports palette, logo size, and safe margin violations. Brand assets and uploaded samples return 403 for AI image editing. Invalid designs return 422.
- PASS: Uvicorn starts with reload on `http://127.0.0.1:8000` using the standard command. Vite is running on localhost:5173 and its /api proxy reaches the restarted Brand Copilot API. Welcome placeholder was visibly rendered in Brave during the initial validation.
- PASS: two-page guidelines PDF rendered and visually inspected.
- PASS: `pip check`.

The original IPv4 port conflict is resolved. After the user stopped the other service, the API started successfully with `cd apps/api && ../../.venv/bin/python -m uvicorn app.main:app --reload --port 8000`. The complete route smoke script and Vite proxy checks passed against this restarted API.

`python scripts/smoke_models.py` ran with these results:

| Check | Result | Reason |
| --- | --- | --- |
| DeepSeek-V4-Pro schema-valid JSON | PASS | Live completion returned JSON matching the requested schema. |
| DeepSeek-V4.1-Flash image + tool call | PASS | Live completion accepted image input and returned a describe_image tool call with schema-valid arguments. |
| Fast image model, 1024 x 1024 | PASS | Live generation returned a valid 1024 x 1024 PNG. |
| Edit model on generated image | PASS | Live edit used this run's generated image and returned a valid 1254 x 1254 PNG. |

All four live checks passed after the user configured `.env`. Pro and Flash now select their own `DEEPSEEK_PRO_ENDPOINT` / `DEEPSEEK_PRO_API_KEY` and `DEEPSEEK_FLASH_ENDPOINT` / `DEEPSEEK_FLASH_API_KEY`, based on their configured deployment names. A local routing check also verified both credential pairs and the legacy shared fallback without printing credential values.

The generated and edited images are at `data/model-smoke/generated.png` and `data/model-smoke/edited.png` (gitignored). Smoke checks call real clients even when USE_STUBS=1. Network-restricted execution initially failed to connect; running with the required network access passed all checks. The original missing-configuration failures and IPv4 conflict are resolved.

Image wrappers follow the official OpenAI Python [generation](https://developers.openai.com/api/reference/python/resources/images/methods/generate) and [editing](https://developers.openai.com/api/reference/python/resources/images/methods/edit) interfaces. Model deployment names and image model identifiers remain configurable in `.env` exactly as contracted.
