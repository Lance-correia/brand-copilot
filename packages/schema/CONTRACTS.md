Contracts
Every agent builds against these shapes. The Studio owner on main may update contracts and regenerate types.
Repo layout
apps/web/                  Vite + React + TypeScript + Fabric.js + zustand
  src/app/                 routing, page shell                        (Prompt 1)
  src/screens/             Welcome, Brand identity                    (Prompt 1)
  src/copilot/             StartModal, VariantsGrid, CopilotPanel, LintPanel (Prompt 1)
  src/use/                 Use screen: canvas, layers, properties, library, export (Prompt 2)
  src/lib/fonts.ts         brand font loading                         (Prompt 2)
  src/api/client.ts        typed API client                           (Prompt 0, then read-only)
  src/types/               generated types                            (Prompt 0, read-only)
apps/api/                  FastAPI, Python 3.11+, SQLite, local files
  app/main.py              app, CORS, router registration             (Prompt 0)
  app/routers/core.py      workspace, asset, brand, lint, design routes (Prompt 3)
  app/routers/generate.py  sample, variants, jobs, image edit, chat routes (Prompt 4)
  app/core/                db and storage helpers                     (Prompt 3)
  app/brand/               kit extraction, lint                       (Prompt 3)
  app/generate/            planner, builder, templates, chat          (Prompt 4)
  app/llm/                 DeepSeek and OpenAI image clients          (Prompt 4)
  app/schema/              generated Pydantic models                  (Prompt 0, read-only)
packages/schema/           JSON Schemas + CONTRACTS.md                (Prompt 0, read-only)
fixtures/                  sample brand, samples, designs, templates  (Prompt 0)
data/                      runtime SQLite + files (gitignored)
Run and environment
• API: cd apps/api && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
• Web: npm run dev (http://127.0.0.1:5173; Vite proxies /api to 127.0.0.1:8000)
• Storage: SQLite at data/app.db; files at data/files/{workspaceId}/{assetId}.{ext}
• Single user, no login.
.env at the repo root:
AZURE_DEEPSEEK_ENDPOINT=
AZURE_DEEPSEEK_API_KEY=
DEEPSEEK_PRO_MODEL=        # Azure deployment name for DeepSeek-V4-Pro
DEEPSEEK_FLASH_MODEL=      # Azure deployment name for DeepSeek-V4.1-Flash
OPENAI_API_KEY=
IMAGE_MODEL_FAST=gpt-image-2.5-flare
IMAGE_MODEL_EDIT=gpt-image-2.5-sunburst
DATA_DIR=./data
USE_STUBS=1                # 1 = AI steps return fixtures, no keys needed
Conventions
• IDs are prefixed strings: ws_, ast_, des_, lay_, job_, thr_, msg_.
• Coordinates are canvas pixels, origin top-left. Layer order is array order; the first layer is at the bottom.
• Colors and fonts are referenced by brand-kit token, never by raw hex or family name, so a brand-kit change updates every design.
• Templates and specs use boxes as [x0, y0, x1, y1] fractions of the canvas.
• Timestamps are UTC ISO 8601.
Data shapes
Workspace
{"id": "ws_01", "name": "Lumen Coffee", "createdAt": "2026-10-17T10:00:00Z", "brandKitConfirmed": false}
Asset
kind: logo | font | image | icon | guideline | sample. source: brand_asset | generated | upload. For fonts, meta holds {"family": "...", "weight": 700}.
{"id": "ast_01", "workspaceId": "ws_01", "kind": "logo", "source": "brand_asset", "filename": "logo-dark.svg", "url": "/api/files/ast_01", "mime": "image/svg+xml", "width": 512, "height": 128, "caption": "Lumen wordmark, dark", "tags": ["logo", "dark"], "meta": {}}
BrandKit
Rule check: palette | font | contrast | safe_margin | logo_min_size | logo_clear_space | text_overflow | manual. Logo variant: dark (for light backgrounds) | light (for dark backgrounds). Logo clearSpace is a multiple of the logo's height.
{
  "workspaceId": "ws_01",
  "colors": [
    {"token": "primary", "hex": "#C8553D", "role": "accent"},
    {"token": "ink", "hex": "#1B1B1F", "role": "text"},
    {"token": "paper", "hex": "#FBF7F2", "role": "background"}
  ],
  "fonts": [
    {"token": "headline", "family": "Lumen Display", "weight": 700, "assetId": "ast_05", "minSize": 32, "maxSize": 120},
    {"token": "body", "family": "Lumen Text", "weight": 400, "assetId": "ast_06", "minSize": 16, "maxSize": 40}
  ],
  "logos": [{"assetId": "ast_01", "variant": "dark", "minWidth": 120, "clearSpace": 0.5}],
  "safeMarginPct": 6,
  "imageryStyle": "Natural light, warm tones, real people, no posed stock look",
  "voice": "Short, active sentences",
  "rules": [{"id": "COL-01", "text": "Use only palette colors", "check": "palette"}],
  "confirmed": false
}
Design (scene graph)
Layer type: text | image | shape. Layer role: background | hero | headline | subhead | body | cta | cta_bg | logo | decoration. Image layers carry source and assetId; the source decides whether AI may touch them.
{
  "id": "des_01", "workspaceId": "ws_01", "name": "Variant A",
  "width": 1080, "height": 1080,
  "background": {"colorToken": "paper"},
  "layers": [
    {"id": "lay_1", "type": "image", "role": "hero", "x": 0, "y": 0, "w": 1080, "h": 640, "rotation": 0, "visible": true, "locked": false, "source": "generated", "assetId": "ast_20", "fit": "cover"},
    {"id": "lay_2", "type": "text", "role": "headline", "x": 64, "y": 680, "w": 952, "h": 160, "rotation": 0, "visible": true, "locked": false, "text": "Mornings, slowed down", "fontToken": "headline", "fontSize": 88, "colorToken": "ink", "align": "left"},
    {"id": "lay_3", "type": "shape", "role": "cta_bg", "x": 64, "y": 900, "w": 320, "h": 96, "rotation": 0, "visible": true, "locked": false, "shape": "rect", "fillToken": "primary", "radius": 48},
    {"id": "lay_4", "type": "image", "role": "logo", "x": 856, "y": 936, "w": 160, "h": 40, "rotation": 0, "visible": true, "locked": false, "source": "brand_asset", "assetId": "ast_01", "fit": "contain"}
  ]
}
EditOp
index on add_layer is optional (default: top).
{"op": "add_layer", "layer": <Layer>, "index": 4}
{"op": "update_layer", "layerId": "lay_2", "props": {"text": "New headline"}}
{"op": "remove_layer", "layerId": "lay_3"}
{"op": "reorder_layer", "layerId": "lay_4", "index": 0}
{"op": "replace_image", "layerId": "lay_1", "assetId": "ast_21", "source": "brand_asset"}
{"op": "set_background", "background": {"colorToken": "primary"}}
LintViolation
severity: error | warning. fix is empty when no deterministic fix exists.
{"ruleId": "COL-01", "severity": "error", "layerId": "lay_2", "message": "Color #FF0000 is not in the palette", "fix": [{"op": "update_layer", "layerId": "lay_2", "props": {"colorToken": "ink"}}]}
DesignSpec (output of sample analysis)
{"aspect": "1:1", "regions": [{"role": "hero", "box": [0, 0, 1, 0.6]}, {"role": "headline", "box": [0.06, 0.63, 0.94, 0.78]}], "hierarchy": ["hero", "headline", "cta", "logo"], "mood": "bright, unhurried", "imageryStyle": "lifestyle photo, morning light", "observedColors": ["#F2C14E", "#1B1B1F"]}
Template (fixtures/templates/*.json)
{"id": "hero-top", "name": "Hero top, text below", "aspect": "1:1", "width": 1080, "height": 1080, "slots": [{"role": "hero", "kind": "image", "box": [0, 0, 1, 0.6]}, {"role": "headline", "kind": "text", "box": [0.06, 0.63, 0.94, 0.78]}, {"role": "cta", "kind": "text", "box": [0.06, 0.83, 0.36, 0.92]}, {"role": "logo", "kind": "image", "box": [0.78, 0.86, 0.94, 0.92]}]}
Job
status: queued | running | done | error. designs grows as each variant finishes.
{"id": "job_01", "status": "running", "progress": "Generating images 3/6", "designs": [], "error": null}
HTTP API
All paths sit under /api. Errors return {"error": "message"} with a 4xx or 5xx status.
Method
Path
Body
Returns
Owner
POST
/workspaces
{name}
Workspace
Prompt 3
GET
/workspaces

Workspace[]
Prompt 3
GET
/workspaces/{ws}

Workspace
Prompt 3
POST
/workspaces/{ws}/assets
multipart: file, kind, tags? (comma-separated folder tags)
Asset
Prompt 3
GET
/workspaces/{ws}/assets?kind=

Asset[]
Prompt 3
DELETE
/assets/{id}

204
Prompt 3
GET
/files/{assetId}

file bytes
Prompt 3
POST
/workspaces/{ws}/brand-kit/extract

BrandKit (unconfirmed)
Prompt 3
GET
/workspaces/{ws}/brand-kit

BrandKit, or 404
Prompt 3
PUT
/workspaces/{ws}/brand-kit
BrandKit
BrandKit
Prompt 3
POST
/workspaces/{ws}/lint
Design
LintViolation[]
Prompt 3
GET
/workspaces/{ws}/designs

Design[]
Prompt 3
POST
/workspaces/{ws}/designs
Design
Design
Prompt 3
GET
/designs/{id}

Design
Prompt 3
PUT
/designs/{id}
Design
Design
Prompt 3
POST
/workspaces/{ws}/samples
multipart: file
{asset, spec}
Prompt 4
POST
/workspaces/{ws}/decompose
{sampleAssetId}
{jobId}; the Job's designs[0] is the layered design
Prompt 4
POST
/workspaces/{ws}/variants
{sampleAssetId, brief?}
{jobId}
Prompt 4
GET
/jobs/{jobId}

Job
Prompt 4
POST
/workspaces/{ws}/images/edit
{assetId, instruction}
Asset
Prompt 4
POST
/workspaces/{ws}/chat
{design, selection, message}
{reply, ops}
Prompt 4
Shared Python helpers
Prompt 0 creates these with simple working versions; Prompt 3 hardens them without changing signatures; Prompt 4 imports them.
• app.core.storage.save_asset(ws_id, data: bytes, filename, kind, source, meta=None) -> Asset
• app.core.storage.get_asset(asset_id) -> Asset and asset_path(asset_id) -> Path
• app.core.storage.list_assets(ws_id, kind=None) -> list[Asset]
• app.core.storage.get_brand_kit(ws_id) -> BrandKit
• app.brand.lint.lint_design(design, kit) -> list[LintViolation]
Frontend interfaces
src/use/canvasStore.ts (Prompt 2 owns) exports a zustand hook useCanvasStore:
design: Design | null
selection: string[]                                   // layer ids
proposal: { ops: EditOp[]; before: Design } | null
load(design: Design): void
applyOps(ops: EditOp[], opts?: { proposal?: boolean }): void
acceptProposal(): void
rejectProposal(): void
undo(): void
redo(): void
• src/use/index.ts (Prompt 2) exports renderThumbnail(design: Design, kit: BrandKit, maxSize?: number): Promise<string>, returning a PNG data URL.
• src/copilot/index.ts (Prompt 1) exports StartModal, VariantsGrid, CopilotPanel and LintPanel. None take required props; they read the workspace id from the route and state from useCanvasStore.
• src/lib/fonts.ts exports loadBrandFonts(kit: BrandKit): Promise<void> and fontFamily(font: FontToken): string. Scene graphs retain font tokens; rendering resolves them to asset/weight-specific FontFace families so switching brands cannot replace another brand's typeface.
Hard rules
• Brand-asset pixels never go to an image model. /images/edit returns 403 for any asset whose source is brand_asset, and the UI shows "Edit with AI" only on generated layers.
• Direct layer edits (text, style, move, swap from the library) make no model calls. Calling /lint is fine; it is deterministic.
• Generated images never contain text: every image prompt ends with "No text, letters, logos or watermarks."
• Every design and op is validated against the schema before it is saved or applied.

Studio contracts (Prompt 6)
• Thread: {id, workspaceId, title, createdAt, messages: Message[]}. IDs use thr_.
• Message: {id, role: user | assistant, text, attachmentAssetIds: string[], designIds: string[], steps: string[], createdAt}. IDs use msg_. Timestamps are UTC ISO 8601.
• Design adds optional label (e.g. "Option B"), version (integer >=1), parentId (a Design id). Agent edits create one new version per edited option per turn, even if several tools edit it. Direct preview edits PUT that same design id without a model call. Parent versions remain available.
• Job adds optional reply (string) and steps (string[]). GET /jobs/{id} exposes the growing step list, progress, designs, and final reply. Polling is the streaming transport.
• POST /workspaces/{ws}/threads {title?} -> Thread (201)
• GET /workspaces/{ws}/threads -> Thread[]
• GET /threads/{id} -> Thread
• POST /threads/{id}/messages {text, attachmentAssetIds?: string[], focusDesignIds?: string[]} -> {jobId} (202)
Attachments first use POST /workspaces/{ws}/samples. Attachment ids must identify uploaded sample images in the same workspace. Focus ids must belong to the same workspace. One message job runs per thread; concurrent submissions return 409.
On completion, persist both user and assistant messages together. The assistant carries reply, result designIds, and steps. On failure, persist an explanatory assistant reply and any successful results; return an error job. Completed threads survive API and browser restarts. Active jobs are in memory and may be lost on API restart.
Studio's loop uses Flash vision/tools, at most 15 model turns and 15 tool executions per message. A bare attachment splits into editable layers and generates four labeled options using the shared pipeline and variant planner/builder. Tool operations and resulting designs are schema-validated; lint fixes run at most twice after each edit. Asset ownership and actual stored source are checked before replacement or image editing. Brand-asset pixels never go to the image model.
Frontend: /w/:id/studio replaces Use; /w/:id/use redirects there, retaining query parameters. /w/:id/editor opens the existing canvas editor without the old modal/variant flow. Studio persists the thread id in the URL and pending job/focus ids locally. Recent design JSON is re-read from storage for each turn so direct edits are current.

Fontless packs: extraction and legacy kit reads resolve uploaded font files first; if none exist, install the bundled OFL DM Sans as an explicitly marked temporary fallback (asset meta.fallback=true, manual FONT-FALLBACK rule). The kit keeps its confirmation state and palette/logos. Studio and Brand identity disclose the substitution; it is never described as an extracted brand font. Missing palette preconditions and failed splitting stop the turn with an actionable error; a failed split is not repeatedly sent to models in the same turn.

Output-quality review branch
• Design adds optional provenance: {referenceAssetId, cleanPlateAssetId?}. Both assets belong to that design's workspace. Versions retain provenance; original and cleaned previews are comparison-only and never modify the design or trigger models.
• Design adds optional quality: {status: ready | needs_review, checkedAt, checks: string[], findings: {code, severity: error | warning, message, layerId?}[]}. This is a report of completed checks, not a guarantee of visual perfection. Recompute it on backend design saves and Studio publication; direct text edits still make no model calls.
• Decomposition stores reusable source analysis and cleanup records in sample/plate Asset.meta, including a versioned content fingerprint, processing times, cleanup method, residual-text findings and whether OCR was available. Cache keys include the analysis/cleanup revision and source bytes. Failed cleanup results are not reused as clean output. Native OCR is optional and its absence is disclosed in quality findings.
• Background cleanup distinguishes flat surfaces from photographic regions. Flat surfaces require no image model. Photographic edits send a same-size alpha mask and a sanitized image, request opaque output, validate coverage, and composite only inside the cleanup mask. Stored brand assets remain forbidden image-model inputs. Local compositing preserves unmasked source pixels.
