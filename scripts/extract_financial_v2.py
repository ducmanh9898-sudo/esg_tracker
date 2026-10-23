"""Parse existing v2 source captures without running OCR again."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.financial_v2 import extract_financial


def main():
    parser = argparse.ArgumentParser(description='Financial table and qualitative note candidates from a source-v2 workspace.')
    parser.add_argument('workspace', type=Path, help='Folder containing canonical.json')
    parser.add_argument('--number-format', choices=['auto', 'vi', 'en'], default='auto')
    args = parser.parse_args()
    try:
        path = extract_financial(args.workspace, number_format=args.number_format)
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({'output': str(path), 'counts': data['counts'], 'issues': len(data['issues']), 'graph_ready': False}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
