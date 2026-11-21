"""Scenario validation and forward model for native OHQ 2D seepage."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import BINARY, DEFAULT, initial_pressure, validate_column
from hydrology.native_grid import grid_trial, sample_at_probe
from hydrology.rainfall import cumulative_depth_m, validate_schedule

SOIL_FIELDS = {
    'ksat_m_day', 'alpha_per_m', 'n', 'theta_res', 'theta_sat',
    'specific_storage_per_m', 'pore_connectivity',
}


def number(value, lower, upper, name):
    if type(value) not in (float, int) or not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f'{name} must be between {lower:g} and {upper:g}.')
    return value


def keys(value, expected, name):
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f'{name} must contain exactly {", ".join(sorted(expected))}.')


def material_spec(material, name):
    if not isinstance(material, dict):
        raise ValueError(f'Material {name} must be an object.')
    theta_key = 'initial_theta' if 'initial_theta' in material else 'initial_pressure_head_m'
    keys(material, SOIL_FIELDS | {theta_key}, f'Material {name}')
    spec = dict(DEFAULT, formulation='cell_centred', **{key: material[key] for key in SOIL_FIELDS})
    if theta_key == 'initial_theta':
        spec['initial_theta'] = material[theta_key]
        return validate_column(spec, 1.)
    # Check constitutive parameters before inverting the native pressure law.
    low = number(spec['theta_res'], .001, .998, 'theta_res')
    high = number(spec['theta_sat'], .002, .999, 'theta_sat')
    spec['initial_theta'] = (low + high)/2
    spec = validate_column(spec, 1.)
    head = number(material[theta_key], -10000., 10., theta_key)
    n = spec['n']
    if head < 0:
        saturation = (1 + (-head * spec['alpha_per_m'])**n)**(1/n - 1)
    else:
        saturation = .999 + head*spec['specific_storage_per_m']/high
    spec['initial_theta'] = low + (high-low)*saturation
    spec = validate_column(spec, 1.)
    if not math.isclose(initial_pressure(spec), head, rel_tol=1e-8, abs_tol=1e-9):
        raise ValueError(f'Material {name} initial pressure is outside the native storage law.')
    return spec


def prepare(scenario):
    keys(scenario, {'width_m', 'cell_height_m', 'materials', 'columns', 'boundaries',
                    'duration_h', 'output_interval_h', 'solver_step_h', 'probes'}, 'Section')
    width = number(scenario['width_m'], .01, 1000., 'width_m')
    dz = number(scenario['cell_height_m'], .001, 100., 'cell_height_m')
    duration = number(scenario['duration_h'], .01, 72., 'duration_h')
    spacing = number(scenario['output_interval_h'], .001, duration, 'output_interval_h')
    step = number(scenario['solver_step_h'], 1/600, min(spacing,.1), 'solver_step_h')
    if duration/spacing > 499 or duration/step > 50000:
        raise ValueError('Use at most 500 saved times and 50000 nominal solver steps.')

    definitions = scenario['materials']
    if not isinstance(definitions, dict) or not 1 <= len(definitions) <= 32:
        raise ValueError('Use 1–32 soil materials.')
    materials = {name: material_spec(value, name) for name, value in definitions.items()}
    columns = scenario['columns']
    if not isinstance(columns, list) or not 2 <= len(columns) <= 32:
        raise ValueError('Use 2–32 horizontal columns.')
    cell_specs, rain_schedules = [], []
    for column in columns:
        keys(column, {'materials', 'rainfall'}, 'Column')
        stack = column['materials']
        if not isinstance(stack, list) or not stack or any(
            not isinstance(name, str) or name not in materials for name in stack
        ):
            raise ValueError('Each column needs a top-to-bottom list of defined material names.')
        cell_specs.append([materials[name] for name in stack])
        rain_schedules.append(validate_schedule(column['rainfall'], duration))
    counts = [len(stack) for stack in cell_specs]
    if sum(counts) > 300 or any(right > left for left, right in zip(counts, counts[1:])):
        raise ValueError('Use at most 300 active cells and a surface descending toward the right.')

    boundaries = scenario['boundaries']
    keys(boundaries, {'surface', 'routing_slope', 'toe_seepage', 'riser_seepage'}, 'Boundaries')
    surface = boundaries['surface']
    if surface not in ('closed_ponding', 'reviewed_infiltration', 'routed_runoff'):
        raise ValueError('Choose closed ponding, reviewed infiltration or routed runoff.')
    slope = number(boundaries['routing_slope'], 0., 10., 'routing_slope')
    if surface == 'routed_runoff' and slope == 0:
        raise ValueError('Routed runoff needs a positive routing slope.')
    if any(type(boundaries[key]) is not bool for key in ('toe_seepage', 'riser_seepage')):
        raise ValueError('Seepage boundary selections must be true or false.')

    probes = scenario['probes']
    if not isinstance(probes, dict) or not 1 <= len(probes) <= 32:
        raise ValueError('Use 1–32 named pressure probes.')
    dx = width/len(counts)
    for name, position in probes.items():
        keys(position, {'x_m', 'elevation_m'}, f'Probe {name}')
        x = number(position['x_m'], dx/2, width-dx/2, f'{name} x_m')
        relative = x/dx - .5
        left, right = math.floor(relative+1e-10), math.ceil(relative-1e-10)
        top = min(counts[left], counts[right])*dz
        number(position['elevation_m'], dz/2, top-dz/2, f'{name} elevation_m')

    spec = dict(cell_specs[0][0], depth_m=max(counts)*dz, cells=max(counts),
                duration_h=duration, output_interval_h=spacing, solver_step_h=step,
                rainfall_mm_h=0., rain_duration_h=0., base='sealed',
                surface_boundary='reviewed_infiltration' if surface == 'reviewed_infiltration'
                else 'closed_ponding')
    return spec, cell_specs, rain_schedules


def simulate_section(folder, scenario, cancelled=lambda: False):
    """Forward evaluation for applications, parameter sampling and calibration."""
    spec, columns, rainfall = prepare(scenario)
    bounds = scenario['boundaries']
    run = grid_trial(Path(folder), spec, [0]*len(columns), cell_specs=columns,
                     rain_schedules=rainfall, width_m=scenario['width_m'],
                     column_cells=[len(column) for column in columns],
                     right_outlet_rows=range(len(columns[-1])) if bounds['toe_seepage'] else (),
                     exposed_step_outlets=bounds['riser_seepage'],
                     route_runoff=bounds['surface']=='routed_runoff',
                     surface_slope=bounds['routing_slope'], cancelled=cancelled)
    if (run['water_balance_max_residual_m3'] > 1e-7
            or min(run['minimum_native_outlet_increment_m3'],
                   run['minimum_native_excess_increment_m3']) < -1e-9):
        raise ValueError('Water balance or one-way discharge check failed.')
    width = scenario['width_m']/len(columns)
    rainfall_total = width*math.fsum(
        cumulative_depth_m({'rainfall_schedule': schedule, 'duration_h': spec['duration_h']},
                           spec['duration_h']) for schedule in rainfall)
    probes = {name: sample_at_probe(run, **position) for name, position in scenario['probes'].items()}
    return dict(analysis='seepage_2d', samples=1, engine_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                rainfall_total_m3=rainfall_total, probes=probes, hydrology=run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('scenario', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.scenario.resolve():
        parser.error('The output path must differ from the scenario path.')
    try:
        scenario = json.loads(args.scenario.read_text())
        result = simulate_section(args.output.parent/(args.output.stem+'_files'), scenario)
    except (OSError, ValueError) as error:
        parser.exit(1, f'Section simulation failed: {error}\n')
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(f'Saved {args.output}')


if __name__ == '__main__':
    main()
