#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'apps/api'))
from app.core.fixtures import seed_workspace
from app.core.storage import list_assets

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--workspace-id', default='ws_lumen')
    parser.add_argument('--name', default='Lumen Coffee')
    args=parser.parse_args()
    workspace=seed_workspace(args.workspace_id, args.name)
    print(f'{workspace.id}: {workspace.name}; {len(list_assets(workspace.id))} assets, brand kit, 3 designs')
