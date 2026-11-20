"""Offline dry-column runtime diagnosis; does not change web/API grid or time limits."""
import argparse
import hashlib
import json
from pathlib import Path
import time

from hydrology.column import ROOT, render, run_engine, summarize_column, validate_column
from validation.cell_centred import profile_difference
from validation.ponding import SPEC, FAILURE_DEPTH, differences, reference


def stopping_reason(details):
    for marker, reason in (
        ('Simulation time exceeded the limit', 'engine_wall_time_limit'),
        ('Maximum number of matrix inversions exceeded', 'matrix_inversion_limit'),
    ):
        if marker in details:return reason
    return 'unclassified'


def trial(folder, spec, engine_seconds):
    """Bypass only the app cell cap for a controlled offline model."""
    if type(engine_seconds) is not int or not 1<=engine_seconds<=900:
        raise ValueError('Use 1 to 900 seconds for the offline engine limit.')
    step=spec['solver_step_h']
    if not isinstance(step,(int,float)) or not 1/1920<=step<=.1 or spec['duration_h']/step>50000:
        raise ValueError('Offline maximum step must be between 1/1920 and 0.1 h, with at most 50000 nominal steps.')
    # Check normal inputs, allowing only the diagnostic grid and smaller-step exceptions.
    validate_column({**spec,'cells':64,'solver_step_h':max(step,1/600)},FAILURE_DEPTH)
    if spec['cells'] not in (64,128):raise ValueError('Diagnostic supports 64 or 128 cells.')
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    # A new run must not inherit a previous run's termination diagnosis.
    (folder/'solution_details.txt').unlink(missing_ok=True)
    model=render(folder,spec)
    script=model.read_text().replace('quantity=write_solution_details,value=No',
                                    'quantity=write_solution_details,value=Yes')
    script=script.replace('quantity=maximum_time_allowed,value=120',
                          f'quantity=maximum_time_allowed,value={engine_seconds}')
    model.write_text(script)
    started=time.monotonic()
    result={'specification':spec,'engine_limit_s':engine_seconds,
            'process_limit_s':engine_seconds+5,'model_sha256':hashlib.sha256(model.read_bytes()).hexdigest()}
    try:
        observations=run_engine(folder,model,wall_time_limit_s=engine_seconds+5)
        result.update(state='completed',hydrology=summarize_column(observations,spec,FAILURE_DEPTH))
    except (ValueError,OSError) as error:
        details=folder/'solution_details.txt'
        result.update(state='failed',message=str(error),
                      stopping_reason=('process_wall_time_limit' if 'OHQ column exceeded its time limit' in str(error)
                                       else stopping_reason(details.read_text() if details.exists() else '')))
    result['elapsed_s']=time.monotonic()-started
    (folder/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/runtime-diagnosis.json'))
    parser.add_argument('--engine-seconds',type=int,default=600)
    parser.add_argument('--cells',type=int,choices=(64,128),default=128)
    steps=parser.add_mutually_exclusive_group()
    steps.add_argument('--half-step',action='store_true',help='Compatibility shorthand for --step-divisions 480.')
    steps.add_argument('--step-divisions',type=int,choices=(240,480,960,1920),
                       help='Maximum time step is 1/N hours; defaults to 240.')
    parser.add_argument('--compare',action='store_true',help='Also compute independent 128/256-cell and temporal references.')
    args=parser.parse_args()
    if not 1<=args.engine_seconds<=900:parser.error('Use 1 to 900 seconds for the offline engine limit.')
    try:
        result=diagnose(args)
    except (ValueError,OSError,KeyboardInterrupt) as error:
        result=json.loads(args.output.read_text()) if args.output.exists() else {}
        result.update(state='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',
                      message=str(error) or 'Interrupted by user.',field_validated=False)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        parser.exit(1,result['message']+'\n')
    if result['trial']['state']!='completed':raise SystemExit(1)


def diagnose(args):
    spec={**SPEC,'cells':args.cells,'formulation':'cell_centred','initial_theta':.2,
          'solver_step_h':1/(480 if args.half_step else (args.step_divisions or 240))}
    folder=args.output.parent/(args.output.stem+'_files')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'state':'running','specification':spec,'field_validated':False},indent=2)+'\n')
    print(f'OHQ {args.cells} cells, engine allowance {args.engine_seconds}s',flush=True)
    result={'trial':trial(folder,spec,args.engine_seconds),'field_validated':False,
            'engine_dependency':json.loads((ROOT/'config/engine.json').read_text())}
    result['state']='comparing' if args.compare and result['trial']['state']=='completed' else result['trial']['state']
    # Persist the native result before an independent comparison starts.
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    if args.compare and result['trial']['state']=='completed':
        print('Independent matched/256-cell and temporal references',flush=True)
        step=spec['solver_step_h']/24
        medium=reference(128,step,spec=spec);fine=reference(256,step,spec=spec)
        temporal=reference(256,step/2,spec=spec)
        matched=medium if args.cells==128 else reference(64,step,spec=spec)
        hydro=result['trial']['hydrology']
        peak=max((abs(a-b),i,j) for i,(x,y) in enumerate(zip(hydro['profiles'],matched['profiles']))
                 for j,(a,b) in enumerate(zip(x['pressure_head_m'],y['pressure_head_m'])))
        error,i,j=peak
        result['comparison']={'matched_failure_pressure':differences(hydro,matched),
                              'matched_profile_difference_m':profile_difference(hydro,matched),
                              'matched_profile_peak':{'maximum_profile_difference_m':error,
                                  'time_h':hydro['profiles'][i]['time_h'],'depth_m':hydro['reference_depths_m'][j],
                                  'ohq_pressure_m':hydro['profiles'][i]['pressure_head_m'][j],
                                  'reference_pressure_m':matched['profiles'][i]['pressure_head_m'][j]},
                              'fine_failure_pressure':differences(hydro,fine),
                              'reference_grid_difference':differences(medium,fine),
                              'reference_time_difference':differences(fine,temporal)}
        result.update(matched_reference=matched,fine_reference=fine,reference_half_step=temporal)
    result['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
        ('hydrology/column.py','validation/runtime_diagnosis.py','validation/ponding.py','validation/cell_centred.py','components/cell_centred_column.json')}
    result['state']=result['trial']['state']
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('Saved '+str(args.output),flush=True)
    return result


if __name__=='__main__':main()
