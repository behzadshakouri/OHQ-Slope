"""Controlled factorial diagnosis of the ponding transient pressure difference.

All eight combinations use one independent solver, grid and step. This avoids
confounding a changed boundary/geometry with a changed time integrator. The
production-equivalent combination is also compared to actual pinned OHQ runs.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

from hydrology.column import ROOT, simulate
from validation.ponding import SPEC, FAILURE_DEPTH, differences, reference

PHYSICAL=('centre','arithmetic','complementarity')
PRODUCTION=('top','maximum','smoothed')
KEYS=('head_reference','conductivity','surface_boundary')


def variant(values):return dict(zip(KEYS,values))


def diagnose(folder,cells=32,step_days=.000125):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    cases={}
    for values in itertools.product(*zip(PHYSICAL,PRODUCTION)):
        label='/'.join(values)
        print('Independent variant: '+label,flush=True)
        cases[values]=reference(cells,step_days,**variant(values))
    physical=cases[PHYSICAL];production=cases[PRODUCTION]
    signed=[a['head_m']-b['head_m'] for a,b in zip(production['pressure_history'],physical['pressure_history'])]
    peak=max(range(len(signed)),key=lambda i:abs(signed[i]))
    effects=[]
    for axis,name in enumerate(KEYS):
        changed=list(PRODUCTION);changed[axis]=PHYSICAL[axis];changed=tuple(changed)
        effects.append({'change':name,'from':PRODUCTION[axis],'to':PHYSICAL[axis],
            'signed_pressure_change_at_common_peak_m':cases[changed]['pressure_history'][peak]['head_m']-production['pressure_history'][peak]['head_m'],
            'remaining_difference_from_physical':differences(cases[changed],physical)})
    # Numerical mismatch is checked with the *same discrete laws*, separately
    # from the physical boundary comparison. Never interpret this as independent
    # confirmation that the production laws are physically correct.
    ohq=[]
    for multiplier in (1.,.5,.25):
        spec={**SPEC,'cells':cells,'solver_step_h':SPEC['solver_step_h']*multiplier}
        print(f'OHQ time refinement: step {spec["solver_step_h"]:g} h',flush=True)
        case=simulate(folder/f'ohq-step-{multiplier}',spec,FAILURE_DEPTH)
        ohq.append({'solver_step_h':spec['solver_step_h'],
                    'difference_from_matched_independent_solver':differences(case,production),
                    'difference_from_physical_reference':differences(case,physical),
                    'water_balance_max_residual_m3':case['water_balance_max_residual_m3'],
                    'engine_binary_sha256':case['engine_binary_sha256']})
    print('Independent grid/time refinement',flush=True)
    fine=reference(64,step_days,**variant(PHYSICAL))
    finer=reference(128,step_days,**variant(PHYSICAL))
    temporal=reference(128,step_days/2,**variant(PHYSICAL))
    production_fine=reference(64,step_days,**variant(PRODUCTION))
    production_finer=reference(128,step_days,**variant(PRODUCTION))
    return {'specification':SPEC,'cells':cells,'step_days':step_days,'failure_depth_m':FAILURE_DEPTH,
        'common_peak_time_h':physical['pressure_history'][peak]['time_h'],
        'production_minus_physical_pressure_at_common_peak_m':signed[peak],
        'single_changes_from_production':effects,
        'variants':[{'variant':variant(values),
                     'difference_from_physical':differences(case,physical),
                     'pressure_at_common_peak_m':case['pressure_history'][peak]['head_m'],
                     'water_balance_max_residual_m3':case['water_balance_max_residual_m3']} for values,case in cases.items()],
        'ohq_time_refinement':ohq,
        'physical_reference_grid_differences':[differences(physical,fine),differences(fine,finer)],
        'physical_reference_time_difference':differences(finer,temporal),
        'production_law_grid_differences':[differences(production,production_fine),differences(production_fine,production_finer)],
        'production_vs_physical_under_refinement':[differences(a,b) for a,b in ((production,physical),(production_fine,fine),(production_finer,finer))],
        'production_column_validated':False,
        'interpretation':'Single changes are conditional effects; they need not add up because the factors interact. Matched-law agreement tests implementation, not physical validity.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/ponding-ablation.json'))
    args=parser.parse_args()
    result=diagnose(args.output.parent/(args.output.stem+'_files'))
    result['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
        ('validation/ponding.py','validation/ponding_ablation.py','hydrology/column.py','OpenHydroQual/resources/unsaturated_soil.json')}
    result['engine_dependency']=json.loads((ROOT/'config/engine.json').read_text())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved '+str(args.output),flush=True)


if __name__=='__main__':main()
