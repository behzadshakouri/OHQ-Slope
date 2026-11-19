"""Run a slope scenario without the web interface."""
import argparse
import json
from pathlib import Path
from backend.workflow import execute


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def save(data):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary=args.output.with_suffix(args.output.suffix+'.tmp')
        temporary.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
        temporary.replace(args.output)
    request=None
    try:
        request = json.loads(args.scenario.read_text())
        save({'state':'running','request':request})
        workdir=args.output.parent/(args.output.stem+'_files')
        workdir.mkdir(parents=True,exist_ok=True)
        result = execute(request,workdir)
    except KeyboardInterrupt:
        save({'state':'cancelled','request':request})
        parser.exit(130,'Run cancelled.\n')
    except (OSError, ValueError) as error:
        if request is not None:save({'state':'failed','scenario_file':str(args.scenario),'message':str(error)})
        parser.exit(1, f'Calculation failed: {error}\n')
    save({'state':'completed','request':request,'result':result})
    print(f'Saved {result["samples"]} realizations to {args.output}')

if __name__ == '__main__':main()
