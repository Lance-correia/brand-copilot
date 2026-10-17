"""Build and run one local Studio process, UI and API on 127.0.0.1:8000."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-build',action='store_true',help='Reuse an existing production web build.')
    args=parser.parse_args()
    os.chdir(ROOT)
    if not args.skip_build:
        subprocess.run(['npm','run','build'],check=True)
    if not (ROOT/'apps/web/dist/index.html').is_file():
        parser.error('No web build found. Run without --skip-build first.')
    os.environ['SERVE_WEB']='1'
    print('Brand Copilot: http://127.0.0.1:8000 — one local process for the UI and API.',flush=True)
    os.execv(sys.executable,[sys.executable,'-m','uvicorn','app.main:app','--app-dir',str(ROOT/'apps/api'),
                           '--host','127.0.0.1','--port','8000','--timeout-graceful-shutdown','15'])

if __name__=='__main__':main()
