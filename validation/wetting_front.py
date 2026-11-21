"""Assess the synthetic reviewed-infiltration wetting-front benchmark."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import ROOT
from validation.column_sensitivity import metrics, sample_profile
from validation.ponding import reference

BENCHMARK = ROOT / 'models/wetting_front_benchmark.json'
THETA_INCREMENT = 0.02
BALANCE_LIMIT_M3 = 1e-7
LIMITS = {
    'grid': {'pressure_head_m': .03, 'theta': .01, 'arrival_min': 2.},
    'time_step': {'pressure_head_m': .005, 'theta': .002, 'arrival_min': 1.},
}


def arrival_min(series):
    """Find the first upward threshold crossing using saved output."""
    threshold = series[0]['theta'] + THETA_INCREMENT
    for a, b in zip(series, series[1:]):
        if a['theta'] < threshold <= b['theta']:
            fraction = (threshold - a['theta']) / (b['theta'] - a['theta'])
            return 60 * (a['time_h'] + fraction * (b['time_h'] - a['time_h']))
    return None


def compare_points(a, b):
    result = {field: metrics(a, b, field)['maximum_absolute_difference']
              for field in ('pressure_head_m', 'theta')}
    arrivals = [arrival_min(series) for series in (a, b)]
    result['arrival_times_min'] = arrivals
    result['arrival_min'] = abs(arrivals[1] - arrivals[0]) if None not in arrivals else None
    return result


def assess(study):
    benchmark = json.loads(BENCHMARK.read_text())
    if study['state'] != 'completed' or study['study'] != benchmark:
        raise ValueError('Provide a completed study using the packaged wetting-front benchmark.')
    expected = {(n, 1 / step) for n in (16, 32, 64) for step in (240, 480)}
    trials = {}
    residuals = []
    for trial in study['trials']:
        spec = trial['specification']
        key = (spec['cells'], spec['solver_step_h'])
        if key not in expected or key in trials or trial['state'] != 'completed':
            raise ValueError('Expected one completed trial per benchmark grid and time step.')
        if spec != dict(benchmark['column'], cells=key[0], solver_step_h=key[1]):
            raise ValueError('Benchmark trial changed its physical inputs or output spacing.')
        trials[key] = trial
        residual = trial['hydrology']['water_balance_max_residual_m3']
        if not math.isfinite(residual) or residual < 0:
            raise ValueError('Invalid benchmark water-balance residual.')
        residuals.append(residual)
    if set(trials) != expected:
        raise ValueError('Benchmark grid/time matrix is incomplete.')

    comparisons = []
    for axis, first, second in (
        ('coarse_grid', (16, 1/480), (32, 1/480)),
        ('grid', (32, 1/480), (64, 1/480)),
        ('time_step', (64, 1/240), (64, 1/480)),
    ):
        points = {p['id']: compare_points(*(trials[key]['extracted'][p['id']]
                                          for key in (first, second)))
                  for p in benchmark['points']}
        limits = LIMITS.get(axis)
        passed = None if limits is None else all(
            row[name] is not None and row[name] <= limit
            for row in points.values() for name, limit in limits.items())
        comparisons.append(dict(axis=axis, first=first, second=second, points=points,
                                limits=limits, passed=passed))

    maximum_residual = max(residuals)
    balance_passed = maximum_residual <= BALANCE_LIMIT_M3
    accepted = balance_passed and all(row['passed'] is not False for row in comparisons)
    return dict(state='completed', acceptance_status='passed' if accepted else 'failed',
                field_validated=False, fs_computed=False, theta_increment=THETA_INCREMENT,
                water_balance_max_residual_m3=maximum_residual,
                water_balance_limit_m3=BALANCE_LIMIT_M3, water_balance_passed=balance_passed,
                comparisons=comparisons)


def independent_trial(spec, points):
    hydro = reference(spec['cells'], spec['solver_step_h'] / 24, spec=spec,
                      surface_boundary='reviewed_infiltration',
                      failure_depth_m=points[0]['vertical_depth_m'])
    extracted = {p['id']: sample_profile(hydro, p['vertical_depth_m']) for p in points}
    return {'hydrology': hydro, 'extracted': extracted}


def fine_grid_refinement(benchmark):
    """Refine space and time independently over the same saved time grid."""
    points = benchmark['points']
    trials = {}
    for cells in (64, 128, 256):
        for seconds in (7.5, 3.75):
            spec = dict(benchmark['column'], cells=cells, solver_step_h=seconds / 3600)
            run = independent_trial(spec, points)
            hydro = run['hydrology']
            trials[cells, seconds] = dict(
                cells=cells, maximum_step_s=seconds, steps=hydro['steps'],
                water_balance_max_residual_m3=hydro['water_balance_max_residual_m3'],
                extracted=run['extracted'])

    comparisons = []
    pairs = [('grid', (coarse, seconds), (2 * coarse, seconds))
             for coarse in (64, 128) for seconds in (7.5, 3.75)]
    pairs += [('time_step', (n, 7.5), (n, 3.75)) for n in (64, 128, 256)]
    for axis, first, second in pairs:
        a, b = (trials[key]['extracted'] for key in (first, second))
        differences = {point: compare_points(a[point], b[point]) for point in a}
        limits = LIMITS[axis]
        passed = all(row[name] is not None and row[name] <= limit
                     for row in differences.values() for name, limit in limits.items())
        comparisons.append(dict(axis=axis, first=first, second=second,
                                points=differences, limits=limits, passed=passed))
    balance = max(row['water_balance_max_residual_m3'] for row in trials.values())
    return {'trials': list(trials.values()), 'comparisons': comparisons,
            'water_balance_max_residual_m3': balance,
            'water_balance_passed': balance <= BALANCE_LIMIT_M3,
            'scope': 'Independent finite-volume sensitivity at saved times. Finest grid is not an exact reference.'}


def compare_independent(study):
    """Repeat the benchmark with the same discrete laws in the Python solver."""
    independent_trials = []
    matched = []
    for trial in study['trials']:
        spec = trial['specification']
        points = study['study']['points']
        run = independent_trial(spec, points)
        hydro, extracted = run['hydrology'], run['extracted']
        independent_trials.append(dict(trial, **run))
        matched.append({
            'cells': spec['cells'],
            'maximum_step_s': spec['solver_step_h'] * 3600,
            'reference_steps': hydro['steps'],
            'points': {point: compare_points(native, extracted[point])
                       for point, native in trial['extracted'].items()},
        })
    result = assess(dict(study, trials=independent_trials))
    return {'reference_assessment': result, 'matched_native_reference': matched,
            'scope': 'Same discrete laws and maximum time steps. Internal step placement may differ.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('study', type=Path)
    parser.add_argument('--output', type=Path, default=Path('results/wetting-front-assessment.json'))
    parser.add_argument('--require-pass', action='store_true')
    parser.add_argument('--independent', action='store_true',
                        help='Run the independent finite-volume solver at matching grids and steps.')
    parser.add_argument('--fine-grid', action='store_true',
                        help='Run independent 64/128/256-cell refinement at 7.5 and 3.75 seconds.')
    args = parser.parse_args()
    if args.output.resolve() in (args.study.resolve(), BENCHMARK.resolve()):
        parser.error('Output must differ from the study and benchmark inputs.')
    try:
        data = args.study.read_bytes()
        study = json.loads(data)
        result = assess(study)
        if args.independent:
            result['independent'] = compare_independent(study)
        if args.fine_grid:
            result['fine_grid'] = fine_grid_refinement(study['study'])
        result['study_sha256'] = hashlib.sha256(data).hexdigest()
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = dict(state='failed', message=str(error), field_validated=False, fs_computed=False)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Saved {args.output}: {result.get('acceptance_status', result.get('message'))}")
    return int(result['state'] == 'failed'
               or (args.require_pass and result['acceptance_status'] != 'passed'))


if __name__ == '__main__':
    raise SystemExit(main())
