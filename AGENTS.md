# Brand Copilot

A local, single-user AI brand-design copilot. Welcome creates or opens a workspace. Brand identity accepts guidelines, logos, fonts and approved images, and confirms an extracted brand kit. Use is a layered canvas with four on-brand variants, direct layer editing, and a brand library. Only generated images may be edited with AI.

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

API: `cd apps/api && uvicorn app.main:app --reload --port 8000`

Web: `cd apps/web && npm run dev` (port 5173, /api proxies to port 8000).

Validation: `npm run typecheck`; `bash scripts/smoke_stub.sh`; `python scripts/smoke_models.py` (real credentials required, ignores USE_STUBS).

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

- Never edit `packages/schema`, `src/types`, `app/schema`, or another agent's folder. The Phase 0 scaffold is the sole initial writer. Generated files and the typed API client are read-only after handoff.
- Ask the human for contract changes. Read `packages/schema/CONTRACTS.md` before implementation.
- Commit often on your own branch. Use a separate checkout/worktree when multiple agents run simultaneously.
- Brand-asset pixels never go to an image model. Image-edit routes return 403 for brand assets; only generated layers show Edit with AI.
- Direct text/style/move/library edits make no model calls. Lint is deterministic.
- Every image prompt ends with `No text, letters, logos or watermarks.`
- Validate every design and op against JSON Schema before saving or applying. Backend: `app.core.validation.validate_contract`. Frontend: `src/use/validation.ts`. Validate the resulting design after applying ops.
- Keep helper signatures in CONTRACTS.md unchanged. Python models are exported from `app.schema`; `Layer` and `EditOp` are union aliases, with `LAYER_ADAPTER` and `EDIT_OP_ADAPTER` for standalone Pydantic validation. TypeScript imports use `src/types`.
- Phase 0 intentionally leaves feature logic and styling to owners. AI routes return explicit 501 responses with `USE_STUBS=0` until their owners implement them. Stub jobs grow by one design per poll; decomposition produces one design.
