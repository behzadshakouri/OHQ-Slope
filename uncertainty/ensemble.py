"""Deterministic and independent-uniform mechanical uncertainty propagation."""
import math
import random
from stability.infinite_slope import factor_of_safety

PARAMETERS = {
    'cohesion_kpa': (0, 1000, 5.0),
    'friction_deg': (0.01, 89, 30.0),
    'unit_weight_kn_m3': (1, 40, 18.0),
    'slope_deg': (0.1, 89, 30.0),
    'failure_depth_m': (0.01, 100, 2.0),
}

def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number.')
    return value


def validate(request):
    if not isinstance(request, dict):
        raise ValueError('Scenario must be a JSON object.')
    if request.get('mode') not in ('deterministic', 'ensemble'):
        raise ValueError('Choose deterministic or ensemble mode.')
    parameters = request.get('parameters')
    if not isinstance(parameters, dict) or set(parameters) != set(PARAMETERS):
        raise ValueError('Provide exactly the five mechanical parameters.')
    for name, (lo, hi, _) in PARAMETERS.items():
        entry = parameters[name]
        if not isinstance(entry, dict) or set(entry) != {'value', 'min', 'max'}:
            raise ValueError(f'{name} needs value, min, and max.')
        for key in ('value', 'min', 'max'):
            value = finite(entry[key], f'{name}.{key}')
            if not lo <= value <= hi:
                raise ValueError(f'{name}.{key} must be between {lo} and {hi}.')
        if not entry['min'] <= entry['value'] <= entry['max']:
            raise ValueError(f'{name} requires min ≤ value ≤ max.')
    history = request.get('pressure_history')
    if not isinstance(history, list) or not 2 <= len(history) <= 500:
        raise ValueError('Provide 2 to 500 pressure-history rows.')
    previous = -1
    for row in history:
        if not isinstance(row, dict) or set(row) != {'time_h', 'head_m'}:
            raise ValueError('Each pressure row needs time_h and head_m.')
        time = finite(row['time_h'], 'Time')
        head = finite(row['head_m'], 'Pressure head')
        if not 0 <= time <= 100000 or time <= previous or not -10000 <= head <= 100:
            raise ValueError('Times must increase, be nonnegative and ≤100000 h; heads must be between −10000 and 100 m.')
        previous = time
    count = request.get('samples', 1)
    seed = request.get('seed', 42)
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 10000:
        raise ValueError('Sample count must be an integer from 1 to 10000.')
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32-1:
        raise ValueError('Seed must be an integer from 0 to 4294967295.')
    count = count if request['mode'] == 'ensemble' else 1
    if count * len(history) > 1000000:
        raise ValueError('Limit the run to one million sample-time evaluations.')
    return {**request, 'samples': count, 'seed': seed}


def quantile(values, probability):
    values = sorted(values)
    x = (len(values) - 1) * probability
    lower = int(x)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (x - lower)


def run(request, progress=lambda value: None, cancelled=lambda: False):
    request = validate(request)
    rng = random.Random(request['seed'])
    history = request['pressure_history']
    columns = [[] for _ in history]
    minima = []
    crossings = []
    count = request['samples']
    for i in range(count):
        if cancelled():
            raise InterruptedError('Run cancelled.')
        params = {name: (rng.uniform(spec['min'], spec['max'])
                        if request['mode'] == 'ensemble' else spec['value'])
                  for name, spec in request['parameters'].items()}
        series = [factor_of_safety(**params, pressure_head_m=row['head_m']) for row in history]
        minima.append(min(series))
        # First sampled crossing only; no interpolation or continuous-time claim.
        crossings.append(next((row['time_h'] for row, fs in zip(history, series) if fs < 1), None))
        for column, value in zip(columns, series):
            column.append(value)
        if i % max(1, count // 100) == 0:
            progress((i + 1) / count)
    probability = sum(v < 1 for v in minima) / count
    series = [{'time_h': row['time_h'], 'pressure_head_m': row['head_m'],
               'p05': quantile(values, .05), 'median': quantile(values, .5),
               'p95': quantile(values, .95),
               'probability_below_one': sum(v < 1 for v in values) / count}
              for row, values in zip(history, columns)]
    progress(1)
    return {
        'mode': request['mode'], 'samples': count, 'seed': request['seed'],
        'pressure_source': 'prescribed_history', 'ohq_hydrology_used': False,
        'distribution': 'independent uniform mechanical inputs' if request['mode'] == 'ensemble' else 'fixed inputs',
        'series': series, 'minimum_fs': {'p05': quantile(minima, .05),
            'median': quantile(minima, .5), 'p95': quantile(minima, .95)},
        'event_probability': probability,
        'monte_carlo_standard_error': math.sqrt(probability * (1-probability) / count) if request['mode'] == 'ensemble' else None,
        'minimum_fs_samples': minima, 'first_sampled_crossing_h': crossings,
        'assumptions': ['Uniform infinite slope; vertical failure depth; fixed total unit weight.',
            'Pressure is prescribed at the failure plane and shared by all realizations.',
            'Negative head provides no suction strength. No seismic load or deformation.',
            'Probabilities and minima are evaluated at supplied times only.',
            'Zero observed threshold crossings do not establish zero probability.',
            'Results are demonstrations until validated for the intended field setting.'],
    }
