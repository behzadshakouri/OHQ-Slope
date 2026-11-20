"""Offline hydrology-only grid/time study driven by an external case specification."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import time

from hydrology.column import (ROOT, BINARY, render, run_engine, summarize_column,
                              validate_column, map_pressure)


def sample_profile(hydro,depth):
    depths=hydro['reference_depths_m']
    if not depths[0]<=depth<=depths[-1]:raise ValueError('Extraction depth outside cell references.')
    def theta_at(values):
        for i in range(len(depths)-1):
            if depth<=depths[i+1]:
                f=(depth-depths[i])/(depths[i+1]-depths[i])
                return values[i]+f*(values[i+1]-values[i])
        return values[-1]
    return [{'time_h':row['time_h'],'pressure_head_m':map_pressure(row['pressure_head_m'],depths,depth),
             'theta':theta_at(row['theta'])} for row in hydro['profiles']]


def metrics(a,b,field):
    if len(a)!=len(b) or any(abs(x['time_h']-y['time_h'])>1e-8 for x,y in zip(a,b)):
        raise ValueError('Compare identical saved time grids; resample explicitly before comparison.')
    delta=[x[field]-y[field] for x,y in zip(a,b)]
    if not delta or not all(math.isfinite(d) for d in delta):raise ValueError('Missing or nonfinite comparison values.')
    return {'bias':math.fsum(delta)/len(delta),'rmse':math.sqrt(math.fsum(d*d for d in delta)/len(delta)),
            'maximum_absolute_difference':max(map(abs,delta)),'final_difference':delta[-1],
            'samples':len(delta),'convention':'first minus second; saved times only'}


def run_trial(folder,spec,points,seconds):
    if type(seconds) is not int or not 1<=seconds<=900:raise ValueError('Use 1–900 engine seconds.')
    if not points:raise ValueError('Specify at least one observation point.')
    for point in points:
        validate_column(spec,point['vertical_depth_m'])
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    (folder/'solution_details.txt').unlink(missing_ok=True)
    model=render(folder,spec)
    model.write_text(model.read_text().replace('quantity=write_solution_details,value=No','quantity=write_solution_details,value=Yes')
                     .replace('quantity=maximum_time_allowed,value=120',f'quantity=maximum_time_allowed,value={seconds}'))
    started=time.monotonic();result={'specification':spec,'engine_limit_s':seconds,'fs_computed':False,
                                    'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest()}
    try:
        raw=run_engine(folder,model,wall_time_limit_s=seconds+5)
        hydro=summarize_column(raw,spec,points[0]['vertical_depth_m'])
        # This diagnostic extracts hydrology, never a slip surface or FS.
        hydro['extraction_depth_m']=hydro.pop('failure_depth_m')
        result.update(state='completed',hydrology=hydro,
                      extracted={p['id']:sample_profile(hydro,p['vertical_depth_m']) for p in points})
    except (ValueError,OSError) as error:
        result.update(state='failed',message=str(error))
    result['elapsed_s']=time.monotonic()-started
    (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study',type=Path)
    parser.add_argument('--cells',type=int,nargs='+',default=[16,32,64])
    parser.add_argument('--step-divisions',type=int,nargs='+',default=[240,480])
    parser.add_argument('--engine-seconds',type=int,default=600)
    parser.add_argument('--output',type=Path,default=Path('results/column-sensitivity.json'))
    args=parser.parse_args()
    if args.output.resolve()==args.study.resolve():parser.error('Output must differ from input.')
    if not 1<=args.engine_seconds<=900 or any(not 2<=n<=64 for n in args.cells) or any(n not in (240,480) for n in args.step_divisions):
        parser.error('Use 2–64 cells, step divisions 240/480, and 1–900 engine seconds.')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    result={'state':'running','field_validated':False,'fs_computed':False,'trials':[],
            'input_sha256':hashlib.sha256(args.study.read_bytes()).hexdigest(),
            'source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                ('validation/column_sensitivity.py','hydrology/column.py','hydrology/rainfall.py',
                 'components/column_boundaries.json','components/cell_centred_column.json','components/reviewed_surface.json')},
            'engine_binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            'engine_dependency':json.loads((ROOT/'config/engine.json').read_text())}
    def save():args.output.write_text(json.dumps(result,indent=2)+'\n')
    save()
    try:
        study=json.loads(args.study.read_text());result['study']=study
        if study.get('formulation_role')!='hydrology_only':raise ValueError('External study must declare formulation_role=hydrology_only.')
        ids=[p['id'] for p in study['points']]
        if len(set(ids))!=len(ids):raise ValueError('Observation IDs must be unique.')
        for cells in args.cells:
            for divisor in args.step_divisions:
                spec={**study['column'],'cells':cells,'solver_step_h':1/divisor}
                label=f'cells-{cells}-step-{divisor}'
                print('Running '+label,flush=True)
                trial=run_trial(args.output.parent/(args.output.stem+'_files')/label,spec,study['points'],args.engine_seconds)
                result['trials'].append(trial);save()
                print(label+': '+trial['state']+f" ({trial['elapsed_s']:.1f}s)",flush=True)
        result['state']='completed' if all(t['state']=='completed' for t in result['trials']) else 'failed'
        result['scope']='Hydrology-only numerical sensitivity at supplied extraction depths; no experimental or continuum-accuracy claim.'
    except (ValueError,OSError,KeyError,TypeError,KeyboardInterrupt) as error:
        result.update(state='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',message=str(error) or 'Interrupted by user.')
    save();print('Saved '+str(args.output),flush=True)
    if result['state']!='completed':parser.exit(1,'Study incomplete; inspect explicit trial statuses.\n')


if __name__=='__main__':main()
