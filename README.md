# Brand Copilot

A local, single-user brand-design Studio. Upload your brand once, attach a reference in chat, and explore four editable options. Ask for changes by option label, or focus an option and make a quick text correction in the canvas. See [AGENTS.md](AGENTS.md) for setup, commands, ownership, and hard rules. The exact shared contract is in [CONTRACTS.md](packages/schema/CONTRACTS.md).

`USE_STUBS=1` works without provider credentials. `python scripts/seed.py` creates the Lumen Coffee fixture workspace. `scripts/gen_types.sh` regenerates both language type sets using only Python's standard library; no network or codegen dependencies are needed.

Fixture assets are fictional. Eight brand images, two samples and four generated-image stand-ins are drawn with Pillow. Fonts are DM Serif Display and DM Sans from Google Fonts, supplied with OFL licenses. `scripts/generate_fixtures.py` rebuilds the two-page guidelines PDF, logos, images, kit, three designs and four templates. The third design intentionally references an unknown `off_palette` token, uses an undersized logo, and places text outside the safe margin. Four job variants are copied from the three design fixtures with unique IDs.

Run the API on `127.0.0.1:8000` and open the web app at `http://127.0.0.1:5173` using the commands in AGENTS.md. Vite proxies `/api` to `http://127.0.0.1:8000`.

Validation and model-smoke results: [scripts/SMOKE_RESULTS.md](scripts/SMOKE_RESULTS.md).

DeepSeek deployments can use separate credentials: set `DEEPSEEK_PRO_ENDPOINT`, `DEEPSEEK_PRO_API_KEY`, `DEEPSEEK_PRO_MODEL` and the corresponding `DEEPSEEK_FLASH_*` variables. The chat helper selects credentials using the configured model deployment name. Legacy `AZURE_DEEPSEEK_ENDPOINT` / `AZURE_DEEPSEEK_API_KEY` remain shared fallbacks. Set each endpoint to its OpenAI-compatible base URL.

Run the single live browser demo after starting both apps with `USE_STUBS=0`: `npx playwright install chromium`, then `npm run test:e2e`. It creates a new workspace, calls the configured models, checks direct-edit isolation, and writes a PNG, screenshot and step timings under `test-results/`.

Studio lives at `/w/:workspaceId/studio`; legacy `/use` links redirect there. Threads and completed messages persist in SQLite. Option cards include version history, a deterministic lint badge, multi-option focus, the full editor, and PNG download. Quick preview text fixes save before the next chat turn reads the design. Active jobs are kept in memory and can be interrupted by restarting the API.
