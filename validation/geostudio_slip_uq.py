"""Propagate an illustrative hydraulic prior through a fixed candidate set."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
from pathlib import Path
import random

from stability.bishop import Slice
from stability.section import fixed_surface_history, screen_circular_surfaces
from uncertainty.ensemble import quantile
from validation.geostudio_fixed_slip import digest
from validation.geostudio_native_case import run_case


def propagate(baseline_path, benchmark_path, output_dir, samples, seed, workers):
    baseline = json.loads(baseline_path.read_text())
    benchmark = json.loads(benchmark_path.read_text())
    source = benchmark['runs'][baseline_path.stem]
    if source['input_sha256'] != digest(baseline_path) or not baseline['balance_and_ledger_passed']:
        raise ValueError('The baseline must match the accepted slip benchmark.')
    selection = benchmark['screening']['runs'][baseline_path.stem]['60']
    candidates = [trial['candidate'] for trial in selection['accepted']]
    inputs = baseline['inputs']
    polygon = inputs['archive_geometry']['polygon_m']
    ground = [tuple(point) for point in polygon[1:-1]]
    slices = [Slice(**row) for row in benchmark['slices']]
    material = slices[0]
    nominal = baseline['spec']['ksat_m_day']
    low, high = .8*nominal, 1.2*nominal
    rng = random.Random(seed)
    values = [math.exp(rng.uniform(math.log(low),math.log(high))) for _ in range(samples)]

    def run(item):
        i, value = item
        trial = run_case(output_dir/f'draw_{i+1:03d}',
                         {**inputs,'spec':{**inputs['spec'],'ksat_m_day':value}},
                         baseline['columns'],baseline['max_layers'],
                         baseline['spec']['solver_step_h']*3600,120)
        if not trial['balance_and_ledger_passed']:
            raise ValueError(f'Native balance failed in draw {i+1}.')
        field = trial['native']
        fixed = fixed_surface_history(field,slices,benchmark['slice_base_points_m'])
        screen = screen_circular_surfaces(field,ground,candidates,60,
                                          benchmark['screening']['unit_weight_kn_m3'],
                                          material.cohesion_kpa,material.friction_rad,material.suction_friction_rad)
        if screen['rejected']:
            raise ValueError(f'The fixed candidate set changed in draw {i+1}.')
        return {'ksat_m_day':value,'model_sha256':field['model_sha256'],
                'fixed_surface':[{'time_h':row['time_h'],'factor_of_safety':row['factor_of_safety']}
                                 for row in fixed],
                'screened_minimum':screen['envelope']}

    output_dir.mkdir(parents=True,exist_ok=False)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        draws = list(pool.map(run,enumerate(values)))
    bands = {}
    for metric in ('fixed_surface','screened_minimum'):
        bands[metric] = [
            {'time_h':rows[0]['time_h'],**{key:quantile([row['factor_of_safety'] for row in rows],q)
                                         for key,q in [('p05',.05),('median',.5),('p95',.95)]}}
            for rows in zip(*(draw[metric] for draw in draws),strict=True)]
    return {'description':'Illustrative sensitivity ensemble; input ranges are assumed',
            'baseline_sha256':source['input_sha256'],'benchmark_sha256':digest(benchmark_path),
            'seed':seed,'ksat_range_m_day':[low,high],'distribution':'log_uniform',
            'fixed_screening_candidates':candidates,'draws':draws,'bands':bands}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline',type=Path)
    parser.add_argument('benchmark',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=4)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--workers',type=int,default=2)
    args = parser.parse_args()
    if not 2 <= args.samples <= 100 or not 1 <= args.workers <= 4:
        parser.error('Use 2–100 draws and 1–4 workers.')
    if args.output.resolve() in {args.baseline.resolve(),args.benchmark.resolve()}:
        parser.error('Output must differ from the input files.')
    result = propagate(args.baseline,args.benchmark,args.output.parent/(args.output.stem+'_files'),
                       args.samples,args.seed,args.workers)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')


if __name__ == '__main__':
    main()
