"""Propagate independent hydraulic ranges through the native OHQ 2D grid."""
import argparse
import copy
import json
from pathlib import Path
import random

from hydrology.section import material_spec, prepare, simulate_section
from uncertainty.coupled import sample, validate_ranges
from uncertainty.ensemble import quantile


def run_ensemble(folder, nominal, ranges, samples, seed):
    prepare(nominal)
    if type(samples) is not int or not 2 <= samples <= 100:
        raise ValueError('Use 2–100 realizations.')
    if type(seed) is not int or not 0 <= seed <= 2**32-1:
        raise ValueError('Use an integer seed between 0 and 4294967295.')
    if not isinstance(ranges, dict) or not ranges or not ranges.keys() <= nominal['materials'].keys():
        raise ValueError('Uncertainty ranges must identify existing material zones.')
    normalized = {}
    for name, entries in sorted(ranges.items()):
        if not isinstance(entries, dict) or any(key not in nominal['materials'][name] for key in entries):
            raise ValueError(f'Sample explicitly specified values for material {name}.')
        material = material_spec(nominal['materials'][name], name)
        normalized[name] = validate_ranges(entries, material, 1.)

    rng = random.Random(seed)
    records = []
    for index in range(samples):
        inputs = copy.deepcopy(nominal)
        draws = {name:{field:sample(rng, entry) for field, entry in entries.items()}
                 for name, entries in normalized.items()}
        for name, values in draws.items():
            inputs['materials'][name].update(values)
        try:
            result = simulate_section(Path(folder)/f'{index+1:04d}', inputs)
        except (OSError, ValueError) as error:
            raise ValueError(f'Section realization {index+1} failed: {error}') from error
        records.append(dict(material_values=draws, probes=result['probes'],
                            final_water_budget=result['hydrology']['outlet_history'][-1],
                            model_sha256=result['hydrology']['model_sha256'],
                            balance_residual_m3=result['hydrology']['water_balance_max_residual_m3']))
    bounds = [('p05', .05), ('median', .5), ('p95', .95)]
    series = {}
    for name in nominal['probes']:
        histories = (record['probes'][name] for record in records)
        series[name] = [{'time_h':rows[0]['time_h'], **{
            label:quantile([row['pressure_head_m'] for row in rows], q) for label,q in bounds
        }} for rows in zip(*histories)]
    return dict(analysis='seepage_2d_uncertainty', samples=samples, seed=seed,
                engine_binary_sha256=result['engine_binary_sha256'], ranges=normalized,
                pressure_head_quantiles_m=series, realizations=records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('ranges', type=Path, help='JSON ranges by material and parameter.')
    parser.add_argument('--samples', type=int, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() in (args.scenario.resolve(), args.ranges.resolve()):
        parser.error('The output path must differ from the input paths.')
    try:
        result = run_ensemble(args.output.parent/(args.output.stem+'_files'),
                              json.loads(args.scenario.read_text()), json.loads(args.ranges.read_text()),
                              args.samples, args.seed)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Calculation failed: {error}\n')
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(f'Saved {args.output}')


if __name__ == '__main__':
    main()
