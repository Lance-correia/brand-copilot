# User-workspace split recovery — 2026-10-17

The user's confirmed XERO kit had an empty font list. `nearest_font()` called `min()` on it, so unrelated references failed with the same error. Fontless extraction and legacy-kit loading now install a bundled, explicitly disclosed DM Sans fallback without replacing the uploaded logos, palette or confirmation. Supplying a real brand font remains necessary for accurate typography.

Failed splits stop with an actionable message instead of spending the remaining tool turns repeating the same call. Split-only requests publish an editable Reference card. Short headlines are no longer mistaken for raster logos through perceptual matching. Optional native macOS OCR recovers omitted headline lines and anchors text to its original geometry; other platforms retain Flash vision as the fallback. Flat panels/button fills and their feathered edges are protected from image-model inpainting artifacts.

Verified the user's existing saved reference through the real `/decompose` route in **30.192 s**, retaining both headline lines, CTA, terms and a library logo. Updated its existing Reference card in the saved thread; no re-upload was needed. A final deterministic cleanup also protects compressed, nearly flat button fills. Reconstruction still depends on source quality, model analysis and the available brand font; text-fit and logo-margin lint findings remain on the recovered reference. It is not a pixel-perfect reproduction.

Regression checks: **50 passed, 2 optional live checks skipped** (1.79 s), `npm run typecheck` passed, and `git diff --check` passed. Coverage includes empty-font extraction/repair, one-attempt split failure, split-only publication, short-headline/logo separation, missing-headline OCR recovery, body-font selection and flat-fill edge protection. The earlier complete Studio browser acceptance below was not rerun for this targeted fix; the user's actual saved reference was checked separately with real models and headless Chromium. User subsequently requested a fresh start: runtime brands, assets, designs, threads and their local diagnostic artifacts are cleared after committing this working version. OCR executable caches are retained.

# Chat-first Studio validation — 2026-10-17

Implemented on `main`, committed in working steps, without pushing. The live frontend is at `http://127.0.0.1:5173`, proxying the real-mode API at `127.0.0.1:8000`. Opened the completed Studio conversation in the user's default browser. A separate Docker preview occupies localhost/IPv6 port 5173; the explicit IPv4 URL reaches this checkout.

## Implemented

- Thread and Message JSON Schemas, optional design labels/versions/parents and job reply/steps; regenerated all twelve contracts.
- Four thread/message endpoints, persistent completed message pairs, per-thread job exclusion and growing job progress/steps.
- `app/studio/` bounded Flash vision/tool loop (at most 15 model rounds and 15 executed tools), with the brand kit, asset catalogue, last twenty messages and current focused/mentioned scene graphs.
- Default attachment flow through the shared decomposition pipeline and the existing Pro planner/builder, preserving reference copy and layout ideas and producing Options A–D. Option A receives a generated photo so it can be edited without passing brand pixels to an image model.
- Versioned text, style, layout, image replacement/placement and generated-image edits. Multiple tool operations on an option in one turn produce a single new version. Ops and final designs are schema-validated; deterministic lint repair runs at most twice per edit. Named labels resolve to the newest version even when browsing an older version.
- Brand-asset replacement uses actual stored source and workspace ownership; image editing checks both the layer source and stored asset source before calling the image model.
- Studio thread list, attachment button/drop/paste, live step list, option cards, multi-focus chips, version selectors, lint badges, full editor links, PNG downloads, quick double-click text editing, and a searchable brand-library drawer. Layers/properties are hidden behind Advanced and are read-only there; the separate full editor retains direct editing.
- `/use` redirects to `/studio`, confirmation lands in Studio, and the old StartModal/VariantsGrid/CopilotPanel flow is unmounted. Quick preview text edits save to the same design and flush before the next chat request.
- Replies are plain text and short, with a summary from completed operations when the model produces an overlong answer.

## Validation

- API import: PASS.
- `npm run build` including `tsc --noEmit`: PASS.
- pytest: **39 passed, 2 skipped** (the existing optional live module/caption checks require separate opt-in).
- `npm run test:e2e`: **1 passed**, headless Chromium, real configured providers, no mocked API responses or injected canvas state. Final run took approximately 140 seconds. Earlier complete real run also passed before the reply/lookup refinements.
- Every option and every returned v2 in the final completed thread had **zero deterministic lint errors** (checked after the run).

The single browser script is `e2e/demo.spec.ts`. It covers every requested acceptance item and additionally checks earlier-version preservation, version-chip switching, short replies, the library drawer, PNG download and the legacy route redirect.

| Final live step | Measured wall time |
| --- | --- |
| Brand folder, extract, confirm, land in Studio | 5.854 s |
| Attach without text, live steps, four editable options | 65.709 s |
| B v2: headline and navy background, no image call | 5.070 s |
| C v2: replace photo with tagged product UI asset | 8.569 s |
| A v2: edit generated background, preserve brand pixels | 48.003 s |
| Focus D, double-click correction, zero model routes | 0.546 s |
| Next chat sees the direct correction | 3.616 s |
| Persistence, library drawer, PNG and legacy redirect | 1.487 s |

Four-option timing includes sample upload/analysis, decomposition/inpainting, Pro planning, image generation, lint and the assistant reply. Typical text/background edit: **5.1 s**; library swap: **8.6 s**. Image editing remains the slowest edit (**48.0 s** in the final run).

B returned one B v2 with both the exact requested headline and navy background, preserved B v1, and produced no generated assets or image-edit steps. C returned C v2 with a different library asset tagged `product-ui`, without generating an image. A returned A v2 with a new generated asset whose parent is also generated; the brand logo remained unchanged and direct brand-image editing returned 403. D's double-click fix made zero model-route requests, kept D v1's identity, and the next chat reply contained the corrected text. Ten messages and seven option cards reloaded from the saved thread. No browser exceptions were recorded.

Completed demo: `http://127.0.0.1:5173/w/ws_c3b49b9c47e44b38bb9a3eeae1e1e374/studio?thread=thr_fe063b86d6834eab8f186e29097e4fe2`

Artifacts (gitignored): `test-results/e2e-demo-chat-first-Studio-3781e-s-and-direct-edit-isolation/{studio.png,studio-export.png,timings.json}`. The screenshot and PNG were visually inspected.

## Remaining limits

No requested Studio acceptance check is failing. Live image-model latency varies. Jobs in progress are in memory and can be lost on API restart; completed threads, messages and versions remain in SQLite. Provider failures appear in the job and conversation. Decomposition/inpainting is still model-dependent rather than pixel-perfect. Stub mode supplies fixture options; conversational tool edits use real providers. Vite emits a non-fatal main-bundle size warning (approximately 783 kB before gzip).

The app is running locally for browser review; no public hosting, push, or credential upload was performed.

---

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
