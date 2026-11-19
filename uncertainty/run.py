"""Run a prescribed-pressure scenario without the web interface."""
import argparse
import json
from pathlib import Path
from backend.workflow import execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.scenario.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        workdir=args.output.parent/(args.output.stem+'_files')
        workdir.mkdir(parents=True,exist_ok=True)
        result = execute(request,workdir)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Calculation failed: {error}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'request': request, 'result': result}, indent=2, allow_nan=False)+'\n')
    print(f'Saved {result["samples"]} realizations to {args.output}')

if __name__ == '__main__':main()
