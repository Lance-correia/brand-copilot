# Brand Copilot

A local, single-user AI brand-design copilot. Welcome creates or opens a workspace. Brand identity accepts guidelines, logos, fonts and approved images, and confirms an extracted brand kit. Studio is a persistent chat with four editable options, version history, a canvas preview and a brand library. Only generated images may be edited with AI.

## Run

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r apps/api/requirements.txt
npm ci
cp .env.example .env
python scripts/seed.py
```

API: `cd apps/api && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

Web: `npm run dev` from the root, then open `http://127.0.0.1:5173` (/api proxies to port 8000).

Validation: `npm run typecheck`; `bash scripts/smoke_stub.sh`; `python scripts/smoke_models.py` (real credentials required, ignores USE_STUBS); `npm run test:e2e` (Studio acceptance, real models).

`DATA_DIR` is resolved relative to the repository root, regardless of working directory. Default: SQLite `data/app.db`, assets `data/files/{workspaceId}/{assetId}.{ext}`. Stub startup seeds `ws_lumen` automatically. Seeding is idempotent.

## Ownership

| Owner / branch | Files and folders |
| --- | --- |
| Prompt 0 / main | `packages/schema/`, `fixtures/`, `scripts/`, root setup, `apps/api/app/main.py`, `apps/web/src/api/client.ts`, generated `apps/web/src/types/`, generated `apps/api/app/schema/` |
| Prompt 1 / agent/web-screens | `apps/web/src/app/`, `apps/web/src/screens/`, `apps/web/src/copilot/` |
| Prompt 2 / agent/web-canvas | `apps/web/src/use/`, `apps/web/src/lib/fonts.ts` |
| Prompt 3 / agent/api-core | `apps/api/app/routers/core.py`, `apps/api/app/core/`, `apps/api/app/brand/` |
| Prompt 4 / agent/api-generate | `apps/api/app/routers/generate.py`, `apps/api/app/generate/`, `apps/api/app/llm/` |

## Rules

- The Studio owner on main owns the whole repository. Edit JSON schemas first and regenerate `src/types` and `app/schema` with `scripts/gen_types.sh`; never hand-edit generated files.
- Read and update `packages/schema/CONTRACTS.md` when changing Studio contracts.
- Commit often on your own branch. Use a separate checkout/worktree when multiple agents run simultaneously.
- Brand-asset pixels never go to an image model. Image-edit routes return 403 for brand assets; only generated layers show Edit with AI.
- Direct text/style/move/library edits make no model calls. Lint is deterministic.
- Every image prompt ends with `No text, letters, logos or watermarks.`
- Validate every design and op against JSON Schema before saving or applying. Backend: `app.core.validation.validate_contract`. Frontend: `src/use/validation.ts`. Validate the resulting design after applying ops.
- Keep helper signatures in CONTRACTS.md unchanged. Python models are exported from `app.schema`; `Layer` and `EditOp` are union aliases, with `LAYER_ADAPTER` and `EDIT_OP_ADAPTER` for standalone Pydantic validation. TypeScript imports use `src/types`.
- Studio uses persistent threads and a bounded Flash tool loop. A bare reference produces four editable options; agent changes create versions and direct preview text edits save to the current design. Completed conversations persist; active jobs are in memory.
