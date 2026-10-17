"""Resolve fontless brand packs to an explicit, local fallback, never a guessed brand font."""
from threading import RLock
from app.core import storage
from app.core.config import FIXTURES
from app.core.validation import validate_contract
from app.schema import BrandKit

FONT_LOCK = RLock()
FALLBACK_NOTICE = 'No font files were supplied. DM Sans is a temporary local fallback; replace it with your brand font in Brand identity.'

class BrandSetupError(ValueError):
    """A deterministic brand precondition; retrying a model cannot fix it."""

def _notice(kit: BrandKit, fallback: bool) -> BrandKit:
    data = kit.model_dump(mode='json',exclude_unset=True)
    data['rules'] = [r for r in data['rules'] if r['id'] != 'FONT-FALLBACK']
    if fallback:
        data['rules'].append({'id':'FONT-FALLBACK','text':FALLBACK_NOTICE,'check':'manual'})
    return BrandKit.model_validate(validate_contract('BrandKit',data))

def ensure_fonts(kit: BrandKit) -> BrandKit:
    """Prefer uploaded font files. If there are none, install one bundled OFL font idempotently."""
    if kit.fonts:
        fallback = any(storage.get_asset(f.assetId).meta.get('fallback') for f in kit.fonts)
        return _notice(kit, fallback)
    with FONT_LOCK:
        assets = storage.list_assets(kit.workspaceId, 'font')
        usable = [a for a in assets if storage.asset_path(a.id).is_file()]
        uploaded = [a for a in usable if not a.meta.get('fallback')]
        fallback = not uploaded
        if uploaded:
            choices = uploaded
        else:
            choices = [a for a in usable if a.meta.get('fallbackKey') == 'studio-sans']
            if not choices:
                asset = storage.save_asset(kit.workspaceId, (FIXTURES / 'brand/fonts/DMSans.ttf').read_bytes(),
                    'studio-fallback-DMSans.ttf', 'font', 'brand_asset',
                    {'fallback':True,'fallbackKey':'studio-sans','providedBy':'app'})
                choices = [storage.set_caption(asset.id, 'DM Sans — temporary app-provided fallback, not an extracted brand font', ['font','fallback'])]
        headline, body = choices[0], choices[-1]
        fonts = [
            {'token':'headline','family':str(headline.meta['family']),'assetId':headline.id,
             'weight':700 if fallback else int(headline.meta.get('weight',400)),'minSize':32,'maxSize':120},
            {'token':'body','family':str(body.meta['family']),'assetId':body.id,
             'weight':int(body.meta.get('weight',400)),'minSize':16,'maxSize':40},
        ]
        data = kit.model_dump(mode='json',exclude_unset=True)
        data['fonts'] = fonts
        return _notice(BrandKit.model_validate(validate_contract('BrandKit',data)), fallback)

def require_design_kit(kit: BrandKit):
    if not kit.colors:
        raise BrandSetupError('Your brand kit has no palette colors. Add colors or extract the brand kit in Brand identity, then retry. Your image is already saved.')
    if not kit.fonts:
        raise BrandSetupError('Your brand kit has no usable fonts. Add a font in Brand identity, then retry. Your image is already saved.')
