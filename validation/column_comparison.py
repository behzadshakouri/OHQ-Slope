"""Compare completed column sensitivity runs and coordinate-labelled archive series."""
import argparse
from bisect import bisect_left
import hashlib
import json
from pathlib import Path

from hydrology.column import ROOT
from validation.column_sensitivity import metrics


def match_saved_times(native, reference):
    """Select native rows at archived times without interpolating either series."""
    times = [row['time_h'] for row in native]
    matched = []
    for row in reference:
        target = row['time_h']
        index = bisect_left(times, target - 1e-8)
        if index == len(times) or abs(times[index] - target) > 1e-8:
            raise ValueError('An archived timestamp is absent from the native output.')
        matched.append(native[index])
    return matched


def compare(study,reference):
    if study['state']!='completed' or any(t['state']!='completed' for t in study['trials']):
        raise ValueError('All requested native trials must complete before comparison.')
    points=study['study']['points']
    for p in points:
        if reference['points'][p['id']]['point']!=p:raise ValueError('Archive point mapping differs from the native extraction mapping.')
    trials=study['trials'];physical=None;seen=set()
    for t in trials:
        spec=t['specification'];key=(spec['cells'],spec['solver_step_h'])
        if key in seen:raise ValueError('Duplicate grid/step trial.')
        seen.add(key)
        current={k:v for k,v in spec.items() if k not in ('cells','solver_step_h')}
        if physical is None:physical=current
        if current!=physical:raise ValueError('Refinement comparison requires identical physical inputs.')
    agreement=[]
    for t in trials:
        row={'cells':t['specification']['cells'],'step_h':t['specification']['solver_step_h'],'points':{}}
        for p in points:
            ref=reference['points'][p['id']]['series'];field='theta' if 'theta' in ref[0] else 'pressure_head_m'
            native = match_saved_times(t['extracted'][p['id']], ref)
            row['points'][p['id']]={'quantity':field,**metrics(native,ref,field)}
        agreement.append(row)
    refinement=[]
    def add(a,b,axis):
        refinement.append({'axis':axis,'first':{k:a['specification'][k] for k in ('cells','solver_step_h')},
                           'second':{k:b['specification'][k] for k in ('cells','solver_step_h')},
                           'points':{p['id']:{field:metrics(a['extracted'][p['id']],b['extracted'][p['id']],field)
                                      for field in ('pressure_head_m','theta')} for p in points}})
    for step in sorted({t['specification']['solver_step_h'] for t in trials}):
        rows=sorted((t for t in trials if t['specification']['solver_step_h']==step),key=lambda t:t['specification']['cells'])
        for a,b in zip(rows,rows[1:]):add(a,b,'grid')
    for cells in sorted({t['specification']['cells'] for t in trials}):
        rows=sorted((t for t in trials if t['specification']['cells']==cells),key=lambda t:-t['specification']['solver_step_h'])
        for a,b in zip(rows,rows[1:]):add(a,b,'maximum_time_step')
    return {'state':'completed','field_validated':False,'fs_computed':False,'acceptance_status':'not_assessed',
            'archive_comparisons':agreement,'refinement_comparisons':refinement,
            'scope':'Saved-time differences from an archived numerical model; constitutive, boundary and dimensional differences remain combined.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',type=Path);parser.add_argument('reference',type=Path)
    parser.add_argument('--output',type=Path,default=Path('results/column-comparison.json'));args=parser.parse_args()
    if args.output.resolve() in (args.study.resolve(),args.reference.resolve()):parser.error('Output must differ from inputs.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text('{"state":"running","field_validated":false}\n')
    try:
        result=compare(json.loads(args.study.read_text()),json.loads(args.reference.read_text()))
        result.update(input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (args.study,args.reference)},
                      source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                          ('validation/column_comparison.py','validation/column_sensitivity.py')})
    except (ValueError,OSError,KeyError,TypeError) as error:
        result={'state':'failed','message':str(error),'field_validated':False,'fs_computed':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n');print('Saved '+str(args.output))
    if result['state']=='failed':parser.exit(1,result['message']+'\n')


if __name__=='__main__':main()
