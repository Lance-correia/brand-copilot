# Integration validation — 2026-10-17

Integrated in the main checkout on `main`. Nothing was pushed. All five worktrees were inspected for committed and uncommitted agent/e2e work. The optional `agent/api-decompose`, required-but-missing `agent/api-agent`, and optional `agent/qa` branches were absent; no alternate worktree contained `app/agent`, `routers/agent.py`, or `e2e/`. Per the updated scope, the rebuild step is deferred to the chat-first Studio agent. There is no rebuild button or `/agent` caller in this UI.

## Merges and gates

Branches were merged one at a time in the requested relative order, each with its own merge commit. Every merge imported the API cleanly, passed `tsc --noEmit`, and passed pytest before proceeding. There were no merge conflicts.

| Branch | Merge commit | pytest | Gate wall time (parallel import/pytest and tsc) |
| --- | --- | --- | --- |
| `agent/api-core` | `58ee882` | 23 passed, 1 skipped | 1.7 s |
| `agent/api-generate` | `94f0ef4` | 31 passed, 2 skipped | 1.7 s |
| `agent/web-canvas` | `e34f53d` | 31 passed, 2 skipped | 1.7 s |
| `agent/web-screens` | `c69f0e6` | 31 passed, 2 skipped | 1.9 s |

Installed API dev requirements from `apps/api/requirements-dev.txt`. The two final pytest skips require live-test opt-in; real providers were separately exercised by model smoke and the browser demo.

## Fixes and follow-ups

- Removed the temporary App sidebar. `UseScreen` owns one mount each of StartModal, VariantsGrid, CopilotPanel, and LintPanel. StartModal and VariantsGrid stay mounted so samples, modal state, and job polling survive opening a design.
- Changed lint selection to `useCanvasStore.getState().select()`.
- Fixed Fabric in-place text editing: clicking outside the canvas finishes editing before a toolbar or panel reads the store. The live browser check caught the unsaved-text bug and verified the fix (`a195e9a`).
- Moved decomposition to `app.decompose.pipeline.run_decompose`; `/decompose` imports this canonical entry point. Legacy helper imports remain compatible. An agent router is deferred under the updated scope.
- Standardized the Vite proxy, smoke-script default, docs, and uvicorn instructions on `127.0.0.1:8000`. Repository source contains no port-8001 references.
- Verified the canvas text default line height is already `1.2`, matching lint.
- Verified optional multipart `tags` on upload matches folder upload's normalized folder-name tag. Existing backend tests cover merging caption tags; the browser checks tags for every uploaded asset kind.
- Ran `scripts/gen_types.sh`: ten contracts regenerated without changes. There was no agent schema change to merge.
- Added exactly one Playwright test file, `e2e/demo.spec.ts`, and `npm run test:e2e`. No separate agent flow or larger test suite was implemented.

## Reset and live models

Deleted `data/app.db` and `data/files`, set the local `.env` to `USE_STUBS=0`, ran `scripts/smoke_models.py`, then ran `scripts/seed.py`. Seed result: `ws_lumen`, 19 assets, confirmed brand kit, 3 designs.

| Real-provider smoke check | Result |
| --- | --- |
| DeepSeek-V4-Pro schema-valid JSON | PASS |
| DeepSeek-V4.1-Flash image plus tool call | PASS |
| Fast image generation, 1024×1024 | PASS |
| Image edit using this run's generated image | PASS |

The live smoke run took approximately 35 seconds; per-provider timers were not instrumented. Its images are in `data/model-smoke/`. The initial restricted-network attempt failed; the network-enabled retry passed all four checks. The API was restarted from this checkout on `127.0.0.1:8000` to load real-mode settings; Vite runs on `127.0.0.1:5173`.

## Final checks

| Check | Result | Measured wall time |
| --- | --- | --- |
| API import | PASS | 0.591 s |
| Production build, including `tsc --noEmit` | PASS | 2.246 s |
| pytest | 31 passed, 2 skipped | 1.476 s |
| Type regeneration | PASS, unchanged generated files | 0.066 s |
| Deterministic route smoke | All 21 contracted method/path pairs pass | 0.21 s |
| `pip check` | PASS | Under 1 s |

The deterministic smoke ran in-process through FastAPI TestClient with isolated temporary storage and stubs, leaving the live API and local `.env` in real mode.

## Browser demo

`npm run test:e2e`: **1 passed**, headless Chromium, real providers, no mocked API responses or injected canvas state. The complete test took approximately 69 seconds. The following timings are measured inside the test:

| Step | Wall time |
| --- | --- |
| Welcome and new brand | 0.224 s |
| Folder upload and tags | 0.104 s |
| Extract, confirm, Use | 4.967 s |
| Upload sample and split into layers | 26.462 s |
| Direct text, style, move, and library swap make no AI requests | 0.393 s |
| Edit generated background with AI | 14.565 s |
| Chat edit and accept | 2.468 s |
| Generate 4 variants and open one | 18.523 s |
| Export PNG | 0.056 s |

Verified the mounted modal and panels occur once; uploaded folder tags survive captioning; in-place text, style, move, and logo swap persist; those direct edits cause **zero** requests to `/chat`, `/images`, `/variants`, `/decompose`, or `/agent`; a brand logo edit returns **403**; generated-background AI editing succeeds; chat applies a proposed headline edit after acceptance; four variants finish and one opens; PNG export has a valid PNG signature. The run recorded zero browser exceptions.

Artifacts (gitignored):

- `test-results/e2e-demo-real-model-demo-and-direct-edit-isolation/demo-export.png` — exported 1080×1080 design, visually inspected.
- `test-results/e2e-demo-real-model-demo-and-direct-edit-isolation/demo.png` — final application screenshot.
- `test-results/e2e-demo-real-model-demo-and-direct-edit-isolation/timings.json` — step timings.
- `data/integration-checks.json` — final API/build/pytest/codegen timings.

Earlier iterations corrected ambiguous test selectors for multiple headline blocks, found and fixed the Fabric text-commit bug, and accounted for optional trailing punctuation in model copy. One intermediate run was interrupted after type regeneration triggered Vite refresh during polling. The final run completed with source files stable.

## Remaining limits

No required API-import, TypeScript, pytest, model-smoke, route-smoke, or scoped browser-demo check is failing. The separate agent rebuild is intentionally deferred under the revised instruction.

Decomposition still depends on model geometry and inpainting quality: earlier runs showed text-overflow/contrast lint findings and imperfect removal of source lettering. The browser test verifies editing, persistence, route isolation, and export; it does not certify pixel-perfect reconstruction or OCR-clean background plates. These visual-quality limits remain for the Studio work.

Vite emits a non-fatal bundle-size warning (main JavaScript approximately 773 kB before gzip). The two optional pytest live checks are skipped unless opted in; the four provider checks and complete scoped browser path passed independently with real credentials.
