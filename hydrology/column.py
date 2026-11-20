"""OHQ vertical-column adapter. No engine source edits or external model uploads."""
from bisect import bisect_right
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / 'OpenHydroQual'
BINARY = ROOT / 'build/ohq-console/OpenHydroQual-Console'
DEFAULT = {
    'depth_m': 2.0, 'cells': 16, 'ksat_m_day': 0.5,
    'alpha_per_m': 1.5, 'n': 1.6, 'theta_res': 0.05, 'theta_sat': 0.4,
    'initial_theta': 0.3, 'specific_storage_per_m': 0.01, 'pore_connectivity': 0.5,
    'rainfall_mm_h': 40.0, 'rain_duration_h': 6.0, 'duration_h': 24.0,
    'output_interval_h': 0.25, 'solver_step_h': 1/60,
    'base': 'sealed', 'formulation': 'legacy_top',
}


def validate_column(spec, failure_depth):
    if isinstance(spec,dict):spec={'formulation':'legacy_top',**spec}
    if not isinstance(spec, dict) or set(spec) != set(DEFAULT):
        raise ValueError('Provide the complete supported soil-column specification.')
    for name, value in spec.items():
        if name == 'formulation':
            if value not in ('legacy_top','cell_centred'):
                raise ValueError('Column formulation must be legacy_top or cell_centred.')
            continue
        if name == 'base':
            if value not in ('sealed', 'unit_gradient'):
                raise ValueError('Base must be sealed or unit_gradient.')
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'{name} must be a finite number.')
    bounds = {'depth_m': (.1, 10), 'ksat_m_day': (.001, 10), 'alpha_per_m': (.01, 20),
              'n': (1.05, 5), 'specific_storage_per_m': (.0001, .1),
              'pore_connectivity': (0, 1), 'rainfall_mm_h': (0, 200),
              'duration_h': (.25, 72), 'rain_duration_h': (0, 72),
              'output_interval_h': (.05, 6), 'solver_step_h': (1/600, .1)}
    for key, (lower, upper) in bounds.items():
        if not lower <= spec[key] <= upper:
            raise ValueError(f'{key} must be between {lower} and {upper}.')
    maximum_cells=64 if spec['formulation']=='cell_centred' else 32
    if not isinstance(spec['cells'], int) or not 2 <= spec['cells'] <= maximum_cells:
        raise ValueError(f'Use 2 to {maximum_cells} soil cells for the selected formulation.')
    if not 0 <= spec['theta_res'] < spec['initial_theta'] < spec['theta_sat'] < 1:
        raise ValueError('Require 0 ≤ residual < initial < saturated water content < 1.')
    if spec['theta_res'] == 0:
        raise ValueError('OHQ requires residual moisture greater than zero.')
    if spec['rain_duration_h'] > spec['duration_h']:
        raise ValueError('Rain duration cannot exceed the simulation duration.')
    if spec['solver_step_h'] > spec['output_interval_h'] or spec['duration_h']/spec['solver_step_h'] > 50000:
        raise ValueError('Solver step must not exceed output spacing; use at most 50000 nominal steps.')
    if spec['duration_h']/spec['output_interval_h'] > 499:
        raise ValueError('Use at most 500 output times.')
    depths=reference_depths(spec)
    if not 0 < failure_depth or not depths[0] <= failure_depth <= depths[-1]:
        raise ValueError(f'Failure depth must be positive and within [{depths[0]:g}, {depths[-1]:g}] m, the soil head-reference locations.')
    return dict(spec)


def reference_depths(spec):
    offset=.5 if spec.get('formulation','legacy_top')=='cell_centred' else 0.
    return [(i+offset)*spec['depth_m']/spec['cells'] for i in range(spec['cells'])]


def ready():
    return BINARY.is_file() and os.access(BINARY, os.X_OK) and (BINARY.parent/'build.json').is_file()


def render(folder, spec):
    """One square metre surface, vertical column, no ET or lateral/runoff loss."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    duration = spec['duration_h']/24
    rain_end = spec['rain_duration_h']/24
    # OHQ precipitation records are (start_day, end_day, interval_depth_METRES).
    rain = []
    if rain_end:
        rain.append(f"0,{rain_end:.17g},{spec['rainfall_mm_h']*spec['rain_duration_h']/1000:.17g}")
    if rain_end < duration:
        rain.append(f'{rain_end:.17g},{duration:.17g},0')
    (folder/'rainfall.csv').write_text('\n'.join(rain)+'\n')
    lines = [f'loadtemplate; filename={ENGINE}/resources/main_components.json',
             f'addtemplate; filename={ENGINE}/resources/unsaturated_soil.json',
             f'addtemplate; filename={ROOT}/components/column_boundaries.json',
             'create source;type=Precipitation,name=Rain,timeseries=rainfall.csv',
             'create block;type=Catchment,name=Surface,area=1,depth=0,elevation=0,Slope=0.01,Width=1,ManningCoeff=0.03,depression_storage=0,Runoff_coeff=1,loss_coefficient=0,Precipitation=Rain']
    centred=spec.get('formulation','legacy_top')=='cell_centred'
    if centred:lines.insert(3,f'addtemplate; filename={ROOT}/components/cell_centred_column.json')
    dz = spec['depth_m']/spec['cells']
    for i in range(spec['cells']):
        fields = {'name': f'Soil{i}', 'area': 1, 'depth': dz, 'bottom_elevation': -(i+1)*dz,
                  'theta': spec['initial_theta'], 'theta_res': spec['theta_res'], 'theta_sat': spec['theta_sat'],
                  'alpha': spec['alpha_per_m'], 'n': spec['n'], 'L': spec['pore_connectivity'],
                  'K_sat_original': spec['ksat_m_day'], 'K_sat_scale_factor': 1,
                  'specific_storage': spec['specific_storage_per_m'], 'aniso_ratio': 1}
        lines.append('create block;type=Soil,' + ','.join(f'{k}={v}' for k,v in fields.items()))
    surface_type='Column Centre Surface Link' if centred else 'surfacewater_to_soil_link'
    soil_type='Column Centre Soil Link' if centred else 'soil_to_soil_link'
    lines.append(f'create link;type={surface_type},from=Surface,to=Soil0,name=Infiltration')
    for i in range(spec['cells']-1):
        lines.append(f'create link;type={soil_type},from=Soil{i},to=Soil{i+1},name=Percolation{i}')
    lines.append('create block;type=Column Drainage Collector,name=Drainage')
    if spec['base'] == 'unit_gradient':
        lines.append(f"create link;type=Column Unit Gradient Drain,from=Soil{spec['cells']-1},to=Drainage,name=BasalDrain")
    observations = [('surface_storage', 'Surface', 'Storage'), ('drainage_storage','Drainage','Storage')]
    for i in range(spec['cells']):
        observations += [(f'storage_{i}',f'Soil{i}','Storage'), (f'pressure_{i}',f'Soil{i}','pressure_head'), (f'theta_{i}',f'Soil{i}','theta')]
    for name, obj, quantity in observations:
        lines.append(f'create observation;type=Observation,name={name},object={obj},expression={quantity},observed_data=,error_structure=normal,error_standard_deviation=1')
    settings = {'simulation_start_time':0, 'simulation_end_time':duration,
                'initial_time_step': spec['solver_step_h']/24, 'max_timestep_increase_factor':1,
                'minimum_timestep':1e-10, 'nr_tolerance':1e-10 if centred else 1e-8,
                'maximum_time_allowed':120, 'make_timeseries_uniform':'No',
                'record_results':'No', 'alloutputfile':'', 'observed_outputfile':'observations.csv',
                'write_solution_details':'No', 'n_threads':1}
    for name,value in settings.items():
        lines.append(f'setvalue;object=system,quantity={name},value={value}')
    path = folder/'column.ohq'
    path.write_text('\n'.join(lines)+'\n')
    return path


def parse_raw(path):
    result = {}
    indices = {}
    for line in Path(path).read_text().splitlines():
        if line.startswith('# series '):
            _, _, index, name, _ = line.split()
            indices[int(index)] = name
            result[name] = []
        elif line.strip():
            index, t, value = line.split()
            t, value = float(t)*24, float(value)
            name = indices[int(index)]
            if not math.isfinite(t) or not math.isfinite(value):
                raise ValueError('OHQ produced nonfinite observations.')
            if result[name] and t <= result[name][-1][0]:
                raise ValueError('OHQ raw timestamps are not increasing.')
            result[name].append((t, value))
    if not result or any(len(values)<2 for values in result.values()):
        raise ValueError('OHQ raw observation export is incomplete.')
    return result


def initial_pressure(spec):
    se = max(.001,min(.999,(spec['initial_theta']-spec['theta_res'])/(spec['theta_sat']-spec['theta_res'])))
    m=1-1/spec['n']
    suction=-min((se**(-1/m)-1)**(1/spec['n'])/spec['alpha_per_m'],10000)
    excess=spec['theta_sat']*max(0,(spec['initial_theta']-spec['theta_res'])/(spec['theta_sat']-spec['theta_res'])-.999)/spec['specific_storage_per_m']
    return suction+excess


def set_initial_observations(observations,spec):
    # Pinned OHQ initializes observation containers with a zero placeholder at
    # t=0. Supply the independently known initial state rather than plotting
    # that placeholder as a physical state. Subsequent states come from OHQ.
    initial={'surface_storage':0.0, 'drainage_storage':0.0}
    for i in range(spec['cells']):
        initial.update({f'storage_{i}':spec['depth_m']/spec['cells']*spec['initial_theta'],
                        f'theta_{i}':spec['initial_theta'], f'pressure_{i}':initial_pressure(spec)})
    if set(initial)!=set(observations):
        raise ValueError('OHQ observation names do not match the generated column.')
    placeholders=all(abs(observations[name][0][1])<1e-14 for name in initial)
    for name, value in initial.items():
        if abs(observations[name][0][0])>1e-10:
            raise ValueError('OHQ output is missing the initial time.')
        if not placeholders and abs(observations[name][0][1]-value)>1e-8:
            raise ValueError(f'OHQ initial observation {name} differs from the specified initial state.')
        observations[name][0]=(0.0,value)


def interpolate(series, target):
    if target < series[0][0]-1e-4 or target > series[-1][0]+1e-4:
        raise ValueError('Requested time is outside OHQ output coverage.')
    index=bisect_right(series,(target,math.inf))
    if index==0:return series[0][1]
    if index==len(series):return series[-1][1]
    t0,v0=series[index-1];t1,v1=series[index]
    fraction=max(0,min(1,(target-t0)/(t1-t0)))
    return v0+(v1-v0)*fraction



def map_pressure(heads, depths, target):
    """Interpolate total head at known reference elevations, then remove elevation."""
    if len(heads)!=len(depths) or not depths[0] <= target <= depths[-1]:
        raise ValueError('Failure depth outside available head references.')
    for i in range(len(depths)-1):
        if target <= depths[i+1]:
            fraction=(target-depths[i])/(depths[i+1]-depths[i])
            total0=heads[i]-depths[i]
            total1=heads[i+1]-depths[i+1]
            return total0+(total1-total0)*fraction+target
    return heads[-1]


def run_engine(folder, model, cancelled=lambda:False, *, wall_time_limit_s=125):
    """Run a generated local model using the pinned console and its raw export."""
    if not isinstance(wall_time_limit_s,(int,float)) or isinstance(wall_time_limit_s,bool) or not math.isfinite(wall_time_limit_s) or not 0 < wall_time_limit_s <= 905:
        raise ValueError('Native process wall-time limit must be positive and at most 905 seconds.')
    if not ready():
        raise ValueError('OHQ console is not built. Run python3 scripts/build_ohq.py --qmake /path/to/qmake.')
    build=json.loads((BINARY.parent/'build.json').read_text())
    if build['binary_sha256']!=hashlib.sha256(BINARY.read_bytes()).hexdigest():
        raise ValueError('OHQ binary differs from build provenance; rebuild before running.')
    try:
        subprocess.run([os.sys.executable,str(ROOT/'scripts/check_dependency.py')],check=True,capture_output=True)
    except subprocess.CalledProcessError as error:
        raise ValueError('OHQ source dependency differs from the pin; restore or deliberately update it before running.') from error
    folder=Path(folder).resolve()
    for name in ('raw_observations.txt','observations.csv'):
        (folder/name).unlink(missing_ok=True)
    log=folder/'ohq.log'
    env={**os.environ, 'OMP_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1',
         'OHQ_RAWOBS':str(folder/'raw_observations.txt')}
    with log.open('w') as stream:
        process=subprocess.Popen([str(BINARY),str(model),'--resources',str(ENGINE/'resources')+'/', '--quiet'],
                                 cwd=folder,stdout=stream,stderr=subprocess.STDOUT,env=env)
        started=time.monotonic()
        try:
            while process.poll() is None:
                if cancelled() or time.monotonic()-started > wall_time_limit_s:
                    process.terminate()
                    try:process.wait(timeout=3)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                    if cancelled():raise InterruptedError('Run cancelled.')
                    raise ValueError('OHQ column exceeded its time limit.')
                time.sleep(.05)
        except BaseException:
            # Includes Ctrl+C in the CLI: never leave an OHQ child running.
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()
            raise

    if process.returncode != 0:
        raise ValueError(f'OHQ failed (exit {process.returncode}); see the job hydrology/ohq.log.')
    return parse_raw(folder/'raw_observations.txt')


def simulate(folder, spec, failure_depth, cancelled=lambda:False):
    spec=validate_column(spec,failure_depth)
    folder=Path(folder).resolve()
    model=render(folder,spec)
    observations=run_engine(folder,model,cancelled)
    return summarize_column(observations,spec,failure_depth)


def summarize_column(observations,spec,failure_depth):
    """Map native observations and check conservation; also used by offline diagnostics."""
    set_initial_observations(observations,spec)
    duration=spec['duration_h']
    times=[i*spec['output_interval_h'] for i in range(int(duration/spec['output_interval_h'])+1)]
    if abs(times[-1]-duration)>1e-8:times.append(duration)
    depths=reference_depths(spec)
    history=[];profiles=[]
    for t in times:
        pressures=[interpolate(observations[f'pressure_{i}'],t) for i in range(spec['cells'])]
        history.append({'time_h':t, 'head_m':map_pressure(pressures,depths,failure_depth)})
        profiles.append({'time_h':t, 'pressure_head_m':pressures,
                         'theta':[interpolate(observations[f'theta_{i}'],t) for i in range(spec['cells'])],
                         'surface_storage_m3':interpolate(observations['surface_storage'],t),
                         'drainage_m3':interpolate(observations['drainage_storage'],t)})
    # Check every native output time, including initial and final, not just display samples.
    residuals=[]
    for t,_ in observations['surface_storage']:
        total=interpolate(observations['surface_storage'],t)+interpolate(observations['drainage_storage'],t)
        total+=sum(interpolate(observations[f'storage_{i}'],t) for i in range(spec['cells']))
        expected=spec['depth_m']*spec['initial_theta']+spec['rainfall_mm_h']/1000*min(t,spec['rain_duration_h'])
        residuals.append(total-expected)
    residual=max(abs(v) for v in residuals)
    minimum_surface=min(value for _,value in observations['surface_storage'])
    if spec['formulation']=='cell_centred' and minimum_surface < -1e-10:
        raise ValueError('Cell-centred surface storage became negative; the ponding complementarity check failed.')
    # One square metre area: tolerance is also water-depth equivalent.
    if residual > 1e-4:
        raise ValueError(f'Column water balance failed: maximum residual {residual:.3g} m³ exceeds 1e-4 m³.')
    return {'pressure_history':history, 'specification':spec, 'reference_depths_m':depths,
            'profiles':profiles, 'water_balance_max_residual_m3':residual,
            'minimum_surface_storage_m3':minimum_surface,
            'rainfall_total_m':spec['rainfall_mm_h']*spec['rain_duration_h']/1000,
            'failure_depth_m':failure_depth,
            'formulation':spec['formulation'],
            'pressure_mapping':('Linear total-head interpolation at cell-centre elevations; pressure = total head minus failure-plane elevation.' if spec['formulation']=='cell_centred' else
                               'Linear total-head interpolation using OHQ soil top-elevation references; pressure = total head minus failure-plane elevation.'),
            'component_sha256':hashlib.sha256((ROOT/'components/cell_centred_column.json').read_bytes()).hexdigest() if spec['formulation']=='cell_centred' else None,
            'engine_binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),
            'initial_state_source':'Known initial model inputs replace OHQ time-zero observation placeholders.',
            'build':json.loads((BINARY.parent/'build.json').read_text())}
