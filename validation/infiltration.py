"""Independent, unsaturated fixed-flux Richards comparison (no ponding).

The reference uses conservative cell-centred finite volumes and explicit Heun
time integration. It does not call OHQ or reuse its flux or retention routines.
Depth x and flux q are positive downward: q=K*(1-dpsi/dx), theta_t=-q_x.
This deliberately isolates rainfall input, gravity and nonlinear redistribution
from the production surface-water connector and saturated storage extension.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import BINARY, ENGINE, ROOT, interpolate, run_engine

SPEC = {'length_m': 1.0, 'initial_pressure_m': -1.0,
        'rainfall_m_day': .02, 'duration_days': .2,
        'alpha_per_m': 1.5, 'n': 1.6, 'theta_res': .05,
        'theta_sat': .4, 'ksat_m_day': .5, 'connectivity': .5}
TIMES = (.05, .1, .2)


def water_content(pressure):
    if pressure >= 0:
        raise ValueError('This benchmark supports unsaturated pressures only.')
    s = SPEC
    m = 1 - 1/s['n']
    return s['theta_res'] + (s['theta_sat']-s['theta_res'])*(1+(s['alpha_per_m']*abs(pressure))**s['n'])**(-m)


def properties(theta):
    s = SPEC
    m = 1 - 1/s['n']
    se = (theta-s['theta_res'])/(s['theta_sat']-s['theta_res'])
    # Stay away from OHQ's retention clipping and saturated storage extension.
    if not .001 < se < .999:
        raise ValueError('Reference left the unclipped unsaturated domain.')
    u = (se**(-1/m)-1)**(1/s['n'])
    pressure = -u/s['alpha_per_m']
    capacity = (s['theta_sat']-s['theta_res'])*m*s['n']*s['alpha_per_m']*u**(s['n']-1)*(1+u**s['n'])**(-m-1)
    k = s['ksat_m_day']*se**s['connectivity']*(1-(1-se**(1/m))**m)**2
    return pressure, k, capacity


def reference(cells=128, safety=.15):
    """Integrate a fixed synthetic case; report profiles and conservation error.

    Arithmetic interface K is consistent with the continuum PDE but differs
    from OHQ's maximum-Se interface. Agreement is assessed under refinement,
    rather than forcing identical discrete fluxes.
    """
    if isinstance(cells, bool) or not isinstance(cells, int) or cells < 2:
        raise ValueError('Use at least two reference cells.')
    if not 0 < safety <= .2:
        raise ValueError('Explicit safety factor must be in (0, .2].')
    dx = SPEC['length_m']/cells
    initial = water_content(SPEC['initial_pressure_m'])
    state = [initial]*cells
    t = 0.; steps = 0; maximum_residual = 0.; profiles = []

    def rate(values):
        p = [properties(value) for value in values]
        flux = [SPEC['rainfall_m_day']]
        flux.extend(.5*(a[1]+b[1])*(1-(b[0]-a[0])/dx) for a,b in zip(p,p[1:]))
        flux.append(0.)  # sealed bottom
        return [(a-b)/dx for a,b in zip(flux,flux[1:])], max(k/c for _,k,c in p)

    for target in TIMES:
        while t < target - 1e-14:
            first, diffusivity = rate(state)
            dt = min(target-t, safety*dx*dx/diffusivity)
            predicted = [a+dt*b for a,b in zip(state,first)]
            second, predicted_diffusivity = rate(predicted)
            # Recompute the predictor if wetting increased the local diffusivity.
            dt = min(dt, safety*dx*dx/predicted_diffusivity)
            predicted = [a+dt*b for a,b in zip(state,first)]
            second, _ = rate(predicted)
            state = [a+.5*dt*(b+c) for a,b,c in zip(state,first,second)]
            t += dt; steps += 1
            residual = abs(dx*math.fsum(state)-SPEC['length_m']*initial-SPEC['rainfall_m_day']*t)
            maximum_residual = max(maximum_residual,residual)
        profiles.append({'time_days': target, 'pressure_m': [properties(a)[0] for a in state]})
    return {'cells': cells, 'safety': safety, 'steps': steps,
            'depths_m': [(i+.5)*dx for i in range(cells)], 'profiles': profiles,
            'maximum_water_balance_residual_m': maximum_residual}


def ohq_case(folder, cells=16, step_days=.0002):
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    s = SPEC; dx = s['length_m']/cells
    (folder/'inflow.csv').write_text(f"0,{s['rainfall_m_day']}\n{s['duration_days']},{s['rainfall_m_day']}\n")
    lines = [f'loadtemplate;filename={ENGINE}/resources/main_components.json',
             f'addtemplate;filename={ENGINE}/resources/unsaturated_soil.json']
    for i in range(cells):
        # OHQ head is depth+bottom_elevation+psi. Offset this synthetic
        # benchmark's elevation to put that reference at the cell centre.
        # This does not change the production adapter's top-reference convention.
        lines.append(f"create block;type=Soil,name=Cell{i},area=1,depth={dx},bottom_elevation={-(i+1.5)*dx},theta={water_content(s['initial_pressure_m']):.17g},theta_res=0.05,theta_sat=0.4,alpha=1.5,n=1.6,L=0.5,K_sat_original=0.5,K_sat_scale_factor=1,specific_storage=0.01,aniso_ratio=1" + (',inflow=inflow.csv' if i == 0 else ''))
        for name, quantity in (('pressure','pressure_head'), ('storage','Storage')):
            lines.append(f'create observation;type=Observation,name={name}_{i},object=Cell{i},expression={quantity},observed_data=,error_structure=normal,error_standard_deviation=1')
        if i:
            lines.append(f'create link;type=soil_to_soil_link,from=Cell{i-1},to=Cell{i},name=Flow{i}')
    settings = {'simulation_start_time':0, 'simulation_end_time':s['duration_days'],
                'initial_time_step':step_days, 'max_timestep_increase_factor':1,
                'minimum_timestep':1e-10, 'nr_tolerance':1e-10,
                'maximum_time_allowed':120, 'make_timeseries_uniform':'No',
                'record_results':'No', 'alloutputfile':'', 'observed_outputfile':'observations.csv',
                'write_solution_details':'No', 'n_threads':1}
    lines.extend(f'setvalue;object=system,quantity={k},value={v}' for k,v in settings.items())
    model = folder/'infiltration.ohq'; model.write_text('\n'.join(lines)+'\n')
    observations = run_engine(folder,model)
    # parse_raw reports hours. Skip OHQ's t=0 observation placeholders.
    residuals = []
    for j,(hours,_) in enumerate(observations['storage_0'][1:], start=1):
        storage = math.fsum(observations[f'storage_{i}'][j][1] for i in range(cells))
        residuals.append(abs(storage-s['length_m']*water_content(s['initial_pressure_m'])-s['rainfall_m_day']*hours/24))
    profiles = [{'time_days':t, 'pressure_m':[interpolate(observations[f'pressure_{i}'],t*24) for i in range(cells)]} for t in TIMES]
    for profile in profiles:
        for pressure in profile['pressure_m']:
            properties(water_content(pressure))  # reject clipped/saturated states
    return {'cells':cells, 'step_days':step_days, 'depths_m':[(i+.5)*dx for i in range(cells)],
            'profiles':profiles, 'maximum_water_balance_residual_m':max(residuals)}


def compare(case, fine):
    errors = []
    for profile, ref in zip(case['profiles'],fine['profiles']):
        if profile['time_days'] != ref['time_days']:
            raise ValueError('Comparison timestamps differ.')
        series = list(zip(fine['depths_m'],ref['pressure_m']))
        errors.append(max(abs(p-interpolate(series,x)) for x,p in zip(case['depths_m'],profile['pressure_m'])))
    return {'maximum_profile_difference_m':max(errors),
            'profile_differences_m':errors, 'times_days':list(TIMES)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=Path('results/infiltration-check.json'))
    args = parser.parse_args()
    folder = args.output.parent/(args.output.stem+'_files')
    coarse, fine = reference(64), reference(128)
    temporal = reference(128,.075)
    cases = [ohq_case(folder/str(n),n) for n in (8,16,32)]
    half_step = ohq_case(folder/'32-half-step',32,.0001)
    result = {'specification':SPEC, 'scope':'Unsaturated fixed-flux infiltration with gravity and a sealed base; excludes ponding and the production surface connector.',
              'engine_dependency':json.loads((ROOT/'config/engine.json').read_text()),
              'engine_binary_sha256':hashlib.sha256(BINARY.read_bytes()).hexdigest(),
              'benchmark_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'reference':fine, 'reference_grid_difference':compare(coarse,fine),
              'reference_time_difference':compare(fine,temporal),
              'ohq_time_difference':compare(cases[-1],half_step),
              'checks':[{**case, **compare(case,fine)} for case in cases],
              'rainfall_column_validated':False}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    for case in result['checks']:
        print(f"{case['cells']} OHQ cells: maximum pressure difference {case['maximum_profile_difference_m']:.6g} m")


if __name__ == '__main__': main()
