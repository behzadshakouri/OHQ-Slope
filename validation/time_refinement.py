"""Compare completed offline time-refinement reports without rerunning OHQ."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import ROOT
from validation.cell_centred import profile_difference
from validation.ponding import differences


def compare(reports):
    if len(reports)<3:raise ValueError('Provide at least three completed, successively halved time-step reports.')
    hydrology=[];references=[];specification=None;identity=None;previous=None
    for report in reports:
        trial=report.get('trial',{})
        if report.get('state') in ('failed','running','comparing','interrupted') or trial.get('state')!='completed':
            raise ValueError('Every input must be a completed native run, with any requested comparison finished.')
        hydro=trial['hydrology'];spec=trial['specification'];step=spec['solver_step_h']
        if hydro['specification']!=spec:raise ValueError('Trial and hydrology specifications differ.')
        physical={k:v for k,v in spec.items() if k!='solver_step_h'}
        if physical.get('formulation')!='cell_centred':
            raise ValueError('This diagnostic compares only the cell-centred formulation.')
        current=(report['engine_dependency'],hydro['engine_binary_sha256'],hydro['component_sha256'],
                 hydro['failure_depth_m'],hydro['pressure_mapping'])
        if specification is None:specification=physical;identity=current
        if physical!=specification or current!=identity:
            raise ValueError('Compare identical physical inputs, mapping, components, and engine identities.')
        if not isinstance(step,(int,float)) or not math.isfinite(step) or step<=0:
            raise ValueError('Each maximum step must be finite and positive.')
        if previous is not None and not math.isclose(previous,2*step,rel_tol=1e-12):
            raise ValueError('Reports must be ordered from coarse to fine with a factor of two between steps.')
        previous=step;hydrology.append(hydro)
        # Older diagnostic reports stored the additional 128-cell temporal reference
        # under this name. Match its actual grid and step, not its position in a file.
        for key in ('matched_reference','matched_reference_half_step'):
            if key in report:references.append(report[key])
    matched=[];rows=[]
    for hydro in hydrology:
        spec=hydro['specification']
        ref=next((r for r in references if r['cells']==spec['cells'] and
                  math.isclose(r['step_days']*24,spec['solver_step_h'],rel_tol=1e-12)),None)
        if ref and ref.get('variant')!={'head_reference':'centre','conductivity':'arithmetic','surface_boundary':'complementarity'}:
            raise ValueError('Independent reference uses different discrete equations.')
        matched.append(ref)
        rows.append({'maximum_step_h':spec['solver_step_h'],
                     'water_balance_max_residual_m3':hydro['water_balance_max_residual_m3'],
                     'minimum_surface_storage_m3':hydro['minimum_surface_storage_m3'],
                     'matched_failure_pressure':differences(hydro,ref) if ref else None,
                     'matched_profile_difference_m':profile_difference(hydro,ref) if ref else None})
    changes=[]
    for i,(a,b) in enumerate(zip(hydrology,hydrology[1:])):
        ra,rb=matched[i:i+2]
        changes.append({'coarse_step_h':a['specification']['solver_step_h'],
                        'fine_step_h':b['specification']['solver_step_h'],
                        'ohq_failure_pressure':differences(a,b),
                        'ohq_profile_difference_m':profile_difference(a,b),
                        'reference_failure_pressure':differences(ra,rb) if ra and rb else None,
                        'reference_profile_difference_m':profile_difference(ra,rb) if ra and rb else None})
    ratios=[]
    for a,b in zip(changes,changes[1:]):
        pair={}
        for key,x,y in (
            ('failure_pressure',a['ohq_failure_pressure']['maximum_failure_pressure_difference_m'],
             b['ohq_failure_pressure']['maximum_failure_pressure_difference_m']),
            ('profile',a['ohq_profile_difference_m'],b['ohq_profile_difference_m'])):
            ratio=x/y if y else None
            pair[key]={'difference_ratio':ratio,'empirical_order':math.log2(ratio) if ratio and ratio>0 else None}
        ratios.append(pair)
    return {'specification_without_step':specification,'rows':rows,'successive_changes':changes,
            'halving_ratios':ratios,'finest_reference_comparison':reports[-1].get('comparison'),
            'field_validated':False,'acceptance_status':'not_assessed',
            'scope':'Differences at saved times for this synthetic case; empirical orders are descriptive, not rigorous error bounds or a failure-time validation.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports',type=Path,nargs='+',help='At least three completed reports, coarse to fine.')
    parser.add_argument('--output',type=Path,default=Path('results/time-refinement.json'))
    args=parser.parse_args()
    # Record work in progress before loading inputs, so stale successful results
    # cannot survive an invalid comparison request at this output path.
    if args.output.resolve() in [p.resolve() for p in args.reports]:parser.error('Output must differ from every input.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'state':'running','field_validated':False})+'\n')
    try:
        result=compare([json.loads(p.read_text()) for p in args.reports])
        result.update(state='completed',input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in args.reports},
                      source_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                          ('validation/time_refinement.py','validation/ponding.py','validation/cell_centred.py')})
    except (ValueError,OSError,KeyError,TypeError) as error:
        result={'state':'failed','message':str(error),'field_validated':False}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved '+str(args.output))
    if result['state']=='failed':parser.exit(1,result['message']+'\n')


if __name__=='__main__':main()
