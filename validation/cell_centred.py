"""Verify selectable cell-centred JSON hydrology across synthetic regimes."""
import argparse
import hashlib
import json
from pathlib import Path

from hydrology.column import ROOT, interpolate, simulate
from validation.ponding import SPEC, FAILURE_DEPTH, differences, reference

CASES={
    'ponded_sealed':{},
    'light_rain':{'rainfall_mm_h':10.},
    'initially_drier':{'initial_theta':.2},
    'initially_wetter':{'initial_theta':.36},
    'drained':{'base':'unit_gradient'},
    'no_rain':{'rainfall_mm_h':0.},
}


def profile_difference(case,ref):
    errors=[]
    if len(case['profiles'])!=len(ref['profiles']):raise ValueError('Profile time grids differ.')
    for a,b in zip(case['profiles'],ref['profiles']):
        if a['time_h']!=b['time_h']:raise ValueError('Profile times differ.')
        series=list(zip(ref['reference_depths_m'],b['pressure_head_m']))
        errors.append(max(abs(p-interpolate(series,x)) for x,p in zip(case['reference_depths_m'],a['pressure_head_m'])))
    return max(errors)


def check(folder,name,grids=(8,16,32),reference_cells=128):
    spec={**SPEC,**CASES[name],'formulation':'cell_centred','solver_step_h':1/240}
    step=spec['solver_step_h']/24
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    print(f'{name}: independent {reference_cells//2}/{reference_cells}-cell and temporal refinement',flush=True)
    medium=reference(reference_cells//2,step,spec=spec)
    fine=reference(reference_cells,step,spec=spec)
    temporal=reference(reference_cells,step/2,spec=spec)
    rows=[];baseline=None
    for cells in grids:
        print(f'{name}: OHQ {cells} cells',flush=True)
        ohq=simulate(folder/f'ohq-{cells}',{**spec,'cells':cells},FAILURE_DEPTH)
        matched=reference(cells,step,spec=spec)
        rows.append({'cells':cells,'matched_failure_pressure':differences(ohq,matched),
                     'matched_maximum_profile_difference_m':profile_difference(ohq,matched),
                     'fine_failure_pressure':differences(ohq,fine),
                     'water_balance_max_residual_m3':ohq['water_balance_max_residual_m3'],
                     'reference_water_balance_max_residual_m3':matched['water_balance_max_residual_m3'],
                     'minimum_surface_depth_m':min(p['surface_storage_m3'] for p in ohq['profiles']),
                     'maximum_surface_depth_m':max(p['surface_storage_m3'] for p in ohq['profiles']),
                     'final_drainage_m3':ohq['profiles'][-1]['drainage_m3'],
                     'engine_binary_sha256':ohq['engine_binary_sha256']})
        if cells==grids[-1]:baseline=ohq
    print(name+': OHQ time refinement',flush=True)
    half=simulate(folder/f'ohq-{grids[-1]}-half-step',{**spec,'cells':grids[-1],'solver_step_h':spec['solver_step_h']/2},FAILURE_DEPTH)
    result={'name':name,'specification':spec,'failure_depth_m':FAILURE_DEPTH,'checks':rows,
            'reference_cells':reference_cells,'reference_grid_difference':differences(medium,fine),
            'reference_time_difference':differences(fine,temporal),
            'ohq_time_difference':differences(baseline,half),'field_validated':False}
    (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/cell-centred-check.json'))
    parser.add_argument('--case',choices=tuple(CASES),action='append',help='Run only selected case(s). Defaults to all six.')
    parser.add_argument('--cells',type=int,nargs='+',default=[8,16,32],help='Increasing OHQ grids, up to 64 cells.')
    parser.add_argument('--reference-cells',type=int,default=128,help='Independent fine reference, at least twice the largest OHQ grid.')
    args=parser.parse_args();folder=args.output.parent/(args.output.stem+'_files')
    if args.cells!=sorted(set(args.cells)) or not all(2<=n<=64 for n in args.cells) or args.reference_cells<2*args.cells[-1] or args.reference_cells>512:
        parser.error('Use increasing distinct OHQ grids from 2 to 64 and a reference between twice the largest OHQ grid and 512 cells.')
    result={'cases':[check(folder/name,name,tuple(args.cells),args.reference_cells) for name in (args.case or CASES)],
            'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                ('components/cell_centred_column.json','hydrology/column.py','validation/ponding.py','validation/cell_centred.py')},
            'engine_dependency':json.loads((ROOT/'config/engine.json').read_text()),
            'scope':'Homogeneous 0.5 m synthetic columns; independent implementation, grid/time sensitivity, and conservation checks, not experimental validation.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved '+str(args.output),flush=True)


if __name__=='__main__':main()
