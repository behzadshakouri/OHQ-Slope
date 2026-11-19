"""Run a prescribed-pressure scenario without the web interface."""
import argparse
import json
from pathlib import Path
from uncertainty.ensemble import run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.scenario.read_text())
        result = run(request)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Calculation failed: {error}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'request': request, 'result': result}, indent=2, allow_nan=False)+'\n')
    print(f'Saved {result["samples"]} realizations to {args.output}')

if __name__ == '__main__':main()
