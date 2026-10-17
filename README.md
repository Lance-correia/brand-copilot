# Brand Copilot

Phase 0 foundation for a local, single-user brand-design copilot. See [AGENTS.md](AGENTS.md) for setup, commands, ownership, and hard rules. The exact shared contract is in [CONTRACTS.md](packages/schema/CONTRACTS.md).

`USE_STUBS=1` works without provider credentials. `python scripts/seed.py` creates the Lumen Coffee fixture workspace. `scripts/gen_types.sh` regenerates both language type sets using only Python's standard library; no network or codegen dependencies are needed.

Fixture assets are fictional. Eight brand images, two samples and four generated-image stand-ins are drawn with Pillow. Fonts are DM Serif Display and DM Sans from Google Fonts, supplied with OFL licenses. `scripts/generate_fixtures.py` rebuilds the two-page guidelines PDF, logos, images, kit, three designs and four templates. The third design intentionally references an unknown `off_palette` token, uses an undersized logo, and places text outside the safe margin. Four job variants are copied from the three design fixtures with unique IDs.

The scaffold only applies `update_layer` ops. Other operations throw explicitly until Prompt 2 implements them. Thumbnail and font-loading helpers, screens and copilot components are placeholders. No feature logic or styling is included.

Validation and model-smoke results: [scripts/SMOKE_RESULTS.md](scripts/SMOKE_RESULTS.md). If another service occupies IPv4 port 8000, `uvicorn app.main:app --host ::1 --port 8000` works with the default localhost proxy and smoke URL.

DeepSeek deployments can use separate credentials: set `DEEPSEEK_PRO_ENDPOINT`, `DEEPSEEK_PRO_API_KEY`, `DEEPSEEK_PRO_MODEL` and the corresponding `DEEPSEEK_FLASH_*` variables. The chat helper selects credentials using the configured model deployment name. Legacy `AZURE_DEEPSEEK_ENDPOINT` / `AZURE_DEEPSEEK_API_KEY` remain shared fallbacks. Set each endpoint to its OpenAI-compatible base URL.
