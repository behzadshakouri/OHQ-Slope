"""Native repeated-rainfall verification on a synthetic column, not a field case."""
import argparse
import hashlib
import json
from pathlib import Path

from hydrology.column import ROOT, simulate
from validation.ponding import reference, differences
from validation.cell_centred import profile_difference


def check(folder):
    model=json.loads((ROOT/'models/repeated_rainfall_example.json').read_text())
    spec=model['column'];depth=model['parameters']['failure_depth_m']['value']
    checks=[]
    for base in ('sealed','unit_gradient'):
        legacy=simulate(folder/(base+'-legacy'),{**spec,'base':base,'formulation':'legacy_top'},depth)
        native=[];refs=[]
        for divisor in (240,480):
            s={**spec,'base':base,'solver_step_h':1/divisor}
            native.append(simulate(folder/f'{base}-centred-{divisor}',s,depth))
            refs.append(reference(cells=s['cells'],step_days=1/divisor/24,spec=s,failure_depth_m=depth))
        checks.append({'base':base,'legacy':legacy,'native':native,'independent':refs,
                       'matched_pressure':[differences(a,b) for a,b in zip(native,refs)],
                       'matched_profile_m':[profile_difference(a,b) for a,b in zip(native,refs)],
                       'native_time_change':differences(*native),
                       'independent_time_change':differences(*refs)})
    return {'state':'completed','field_validated':False,'acceptance_status':'not_assessed',
            'scope':'Synthetic rainfall timing and conservation; pressure differences are numerical sensitivity checks, not error bounds.',
            'checks':checks,'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
             ('hydrology/rainfall.py','hydrology/column.py','validation/ponding.py','validation/rainfall_schedule.py',
              'validation/cell_centred.py','models/repeated_rainfall_example.json')},
            'engine_dependency':json.loads((ROOT/'config/engine.json').read_text())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/rainfall-schedule.json'))
    args=parser.parse_args();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text('{"state":"running","field_validated":false}\n')
    try:result=check(args.output.parent/(args.output.stem+'_files'))
    except (ValueError,OSError,KeyboardInterrupt) as error:
        result={'state':'interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',
                'message':str(error) or 'Interrupted by user.','field_validated':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved '+str(args.output))
    if result['state']!='completed':parser.exit(1,result['message']+'\n')


if __name__=='__main__':main()
