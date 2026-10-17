from app.schema import Design, BrandKit, LintViolation
from app.core.validation import validate_contract

def lint_design(design, kit) -> list[LintViolation]:
    design = Design.model_validate(design)
    kit = BrandKit.model_validate(kit)
    violations = []
    colors = {c.token for c in kit.colors}
    logos = {logo.assetId: logo for logo in kit.logos}
    mx, my = design.width * kit.safeMarginPct / 100, design.height * kit.safeMarginPct / 100
    for layer in design.layers:
        field = 'colorToken' if layer.type == 'text' else 'fillToken' if layer.type == 'shape' else None
        if field and getattr(layer, field) not in colors:
            violations.append(LintViolation(ruleId='COL-01', severity='error', layerId=layer.id,
                message=f'Color {getattr(layer, field)} is not in the palette',
                fix=[{'op':'update_layer', 'layerId':layer.id, 'props':{field: 'ink' if layer.type == 'text' else 'primary'}}]))
        if layer.type == 'image' and layer.role == 'logo' and layer.assetId in logos:
            minimum = logos[layer.assetId].minWidth
            if layer.w < minimum:
                violations.append(LintViolation(ruleId='LOGO-01', severity='error', layerId=layer.id,
                    message=f'Logo must be at least {minimum:g}px wide',
                    fix=[{'op':'update_layer','layerId':layer.id,'props':{'w':minimum,'h':layer.h * minimum / layer.w}}]))
        if layer.type == 'text' and (layer.x < mx or layer.y < my or layer.x + layer.w > design.width - mx or layer.y + layer.h > design.height - my):
            violations.append(LintViolation(ruleId='SAFE-01', severity='warning', layerId=layer.id,
                message='Text is outside the safe margin', fix=[]))
    for violation in violations:
        validate_contract('LintViolation', violation)
    return violations
