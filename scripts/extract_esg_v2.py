"""Extract review-only ESG text/table records from a v2 source workspace."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.esg_v2 import extract_esg


def main():
    parser = argparse.ArgumentParser(description='ESG text/table candidates and candidate evidence links; no automatic verdict.')
    parser.add_argument('workspace', type=Path, help='Source-v2 folder containing canonical.json')
    parser.add_argument('--config', type=Path, default=ROOT / 'config/esg_v2.yml')
    parser.add_argument('--number-format', choices=['auto', 'vi', 'en'], default='auto')
    args = parser.parse_args()
    try:
        path = extract_esg(args.workspace, args.config, args.number_format)
        output = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({'output': str(path), 'counts': output['counts'], 'issues': len(output['issues']), 'graph_ready': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
