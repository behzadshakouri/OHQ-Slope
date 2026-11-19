"""Build the pinned OHQ console out of tree; requires Qt6 and native math libraries."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qmake', default=os.environ.get('QMAKE') or shutil.which('qmake6') or shutil.which('qmake'))
    parser.add_argument('--jobs', type=int, default=2)
    args=parser.parse_args()
    if not args.qmake:parser.error('Qt6 qmake not found; pass --qmake /path/to/Qt/gcc_64/bin/qmake.')
    if not 1<=args.jobs<=8:parser.error('Choose 1 to 8 compiler jobs.')
    build=ROOT/'build/ohq-console';build.mkdir(parents=True,exist_ok=True)
    subprocess.run([sys.executable,str(ROOT/'scripts/check_dependency.py')],check=True)
    project=ROOT/'external/OpenHydroQual/terminal/TOpenHydroQual/TOpenHydroQual.pro'
    qt_version=subprocess.check_output([args.qmake,'-query','QT_VERSION'],text=True).strip()
    if not qt_version.startswith('6.'):parser.error('This build requires Qt6 qmake.')
    commands=[[args.qmake,str(project),'CONFIG+=release'],['make',f'-j{args.jobs}']]
    with (build/'build.log').open('w') as log:
        for command in commands:
            completed=subprocess.run(command,cwd=build,stdout=log,stderr=subprocess.STDOUT)
            if completed.returncode:parser.exit(1,f'Build failed. See {build}/build.log\n')
    binary=build/'OpenHydroQual-Console'
    provenance={'engine':json.loads((ROOT/'config/engine.json').read_text()),'qt_version':qt_version,
                'commands':commands, 'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}
    (build/'build.json').write_text(json.dumps(provenance,indent=2)+'\n')
    print(f'Built {binary}')

if __name__=='__main__':main()
