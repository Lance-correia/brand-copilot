"""Studio tool declarations. Implementation reuses the canvas op and generation helpers."""
from app.generate.chat import tool, S, N

D = {'designId': dict(S)}
TOOLS = [
    tool('split_into_layers', 'Read an attached sample into editable text, logo, shape and generated background layers.', assetId=dict(S)),
    tool('generate_options', 'Create four on-brand options from a source design or uploaded sample. Preserve its message and layout ideas.',
         sourceDesignId=dict(S, optional=True), assetId=dict(S, optional=True), n={'type':'integer','enum':[4]}, brief=dict(S, optional=True)),
    tool('update_layer', 'Edit text, style or layout using canvas ops; never image generation for these changes.', **D, layerId=dict(S), props={'type':'object'}),
    tool('add_text_layer', 'Add editable text.', **D, text=dict(S), role={'type':'string','enum':['headline','subhead','body','cta','decoration']},
         fontToken=dict(S), colorToken=dict(S), x=dict(N), y=dict(N), w=dict(N), h=dict(N), fontSize=dict(N, optional=True)),
    tool('remove_layer', 'Remove a layer.', **D, layerId=dict(S)),
    tool('set_background', 'Set the canvas background to a brand color token, and update background panels. No image call.', **D, colorToken=dict(S)),
    tool('replace_image', 'Swap an image layer for an asset id from the catalogue. No image model call.', **D, layerId=dict(S), assetId=dict(S)),
    tool('place_brand_asset', 'Place a brand image/logo/icon as a layer. box is [x0,y0,x1,y1] fractions of canvas.', **D, assetId=dict(S),
         box={'type':'array','items':dict(N),'minItems':4,'maxItems':4}, role={'type':'string','enum':['background','hero','logo','decoration']}),
    tool('edit_generated_image', 'Edit pixels ONLY when both layer and stored asset source are generated. Brand assets are locked.', **D, layerId=dict(S), instruction=dict(S)),
    tool('search_assets', 'Search brand library captions, filenames and folder tags. Search product UI to find product-ui shots.',
         query=dict(S), kind={'type':'string','enum':['logo','font','image','icon','guideline','sample'],'optional':True}),
    tool('run_lint', 'Check deterministic brand rules for one option.', **D),
    tool('reply', 'End the turn with a short accurate account of changes to each option; do not claim unperformed changes.', text={'type':'string','maxLength':500}),
]

SYSTEM = """You are the brand design Studio agent. Work through tools, then reply briefly. Use plain text, no Markdown, at most four short sentences (one per changed option), at most 500 characters. Omit internal ids, font metrics and schema details.
The user names options by A/B/C/D or their labels. Use latestByLabel to find their current design ids.
Pronouns and 'this' refer to focusDesignIds. 'All four' means the latest four option labels.
Use the provided current JSON: direct preview edits may have changed text since the last message.
An attached image without instructions means split_into_layers, then generate_options from that source, then reply.
If the user asks only to clean a reference or make it editable while keeping the existing layout, call split_into_layers and reply. Do not generate options or rewrite its copy.
For other attachments, keep the source message and layout ideas while following the user's brief.
Text/style/layout changes and library swaps ONLY use ops. Never generate options for a simple edit.
A requested background color means set_background with a matching kit token (e.g. navy), not an image edit.
Copy quoted text exactly, without adding punctuation. Make all requested changes before replying.
For a library swap, search_assets first and use replace_image with the returned asset id. Choose a different asset from the current one when a matching alternative exists. Tags like product-ui mean product UI.
Only edit_generated_image may change pixels. Both the image layer AND stored asset must be generated.
editableImageTargets is a verified allow-list from storage. canEditGeneratedImage=true explicitly authorizes edit_generated_image for that exact target. These generated images are editable; their reference/provenance upload does not change that permission. For a new scene in a generated image (such as office at sunrise), call edit_generated_image directly instead of searching the library.
For 'background image', choose the generated background or hero photo, never the logo. Never send brand images to the image model.
Use one designId per tool. If several tools edit the same option in this turn, reuse the original id or returned version id; these resolve to the same draft.
Tools return the current JSON and new ids. Lint fixes run automatically (at most twice) after edits. Only call run_lint when the user asks for a brand check; do not spend rounds checking rules that the tools already repair. Perform the requested edits immediately, usually in one batch of tool calls, then reply.
Do not loop on lint warnings, repeat identical edits, or alter unrequested options. At most 15 tool calls.
Do not call reply alongside mutating tools: finish editing first, then summarize actual results.
If a tool fails, correct its arguments or explain the limit. Do not claim success after a failed tool.
"""
