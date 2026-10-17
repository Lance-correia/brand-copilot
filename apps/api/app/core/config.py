import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[4]
load_dotenv(ROOT / '.env')
_data = Path(os.getenv('DATA_DIR', './data')).expanduser()
DATA_DIR = _data if _data.is_absolute() else ROOT / _data
FIXTURES = ROOT / 'fixtures'

def use_stubs() -> bool:
    return os.getenv('USE_STUBS', '1') == '1'
