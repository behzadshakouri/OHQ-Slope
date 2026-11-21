"""Check a native OHQ soil grid under uniform and localized rainfall."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import BINARY, ROOT, simulate
from hydrology.native_grid import grid_trial, sample_at_probe
from hydrology.rainfall import cumulative_depth_m


def benchmark(folder):
    study = json.loads((ROOT / 'models/wetting_front_benchmark.json').read_text())
    spec = dict(study['column'], cells=8, output_interval_h=.05, surface_boundary='closed_ponding')
    one_d = simulate(folder / 'column-reference', spec, .06)
    rate = spec['rainfall_mm_h']
    uniform = grid_trial(folder / 'uniform', spec, [rate, rate])
    localized = grid_trial(folder / 'localized', spec, [rate, 0])
    control = grid_trial(folder / 'unlinked-control', spec, [rate, 0], link_columns=False)

    def maximum_uniform_difference(quantity):
        return max(abs(x - y) for column in uniform['histories']
                   for native, ref in zip(column, one_d['profiles'])
                   for x, y in zip(native[quantity], ref[quantity]))

    head_error = maximum_uniform_difference('pressure_head_m')
    theta_error = maximum_uniform_difference('theta')
    rainless = localized['histories'][1]
    rainless_control = control['histories'][1]
    gain = rainless[-1]['water_storage_m3'] - rainless[0]['water_storage_m3']
    control_gain = rainless_control[-1]['water_storage_m3'] - rainless_control[0]['water_storage_m3']
    criteria = dict(
        uniform_recovers_column=head_error <= 1e-3 and theta_error <= 1e-4,
        lateral_redistribution=gain > 1e-5 and abs(control_gain) <= 1e-8,
        water_balance=all(run['water_balance_max_residual_m3'] <= 1e-7
                          for run in (uniform, localized, control, one_d)),
    )
    config = json.loads((ROOT / 'config/engine.json').read_text())
    return dict(state='completed', passed=all(criteria.values()), criteria=criteria,
                scope='Native two-column unsaturated OHQ grid with sealed base and ponding.',
                spec=spec, grid_cells=[2, spec['cells']], width_m=.2,
                cell_depth_centers_m=[(j + .5) * spec['depth_m'] / spec['cells']
                                      for j in range(spec['cells'])],
                engine=config, engine_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                max_uniform_head_difference_m=head_error, max_uniform_theta_difference=theta_error,
                rainless_column_storage_gain_m3=gain, unlinked_rainless_column_storage_gain_m3=control_gain,
                uniform=uniform, localized=localized, unlinked_control=control)


def outlet_benchmark(folder):
    study = json.loads((ROOT / 'models/wetting_front_benchmark.json').read_text())
    pulse = dict(study['column'], output_interval_h=.025, surface_boundary='closed_ponding',
                 duration_h=.25, rain_duration_h=.125, specific_storage_per_m=.03,
                 initial_theta=.399999)
    runs = {}
    for nx, nz, step_s in ((2, 8, 15), (4, 16, 15), (4, 16, 7.5)):
        spec = dict(pulse, cells=nz, solver_step_h=step_s/3600)
        name = f'{nx}x{nz}-{step_s:g}s'
        run = grid_trial(folder / name, spec, [15] * (nx//2) + [0] * (nx//2),
                         right_outlet_rows=range(nz//2, nz))
        runs[name] = dict(spec=spec, grid_cells=[nx, nz], **run)

    dry = dict(pulse, cells=8, initial_theta=.2)
    closed = grid_trial(folder / 'suction-control', dry, [0, 0], right_outlet_rows=range(4, 8))
    discharges = [run['outlet_history'][-1]['cumulative_discharge_m3'] for run in runs.values()]
    temporal = abs(discharges[2] - discharges[1])
    spatial = abs(discharges[1] - discharges[0])
    criteria = dict(
        drains_under_positive_pressure=min(discharges) > 1e-5,
        closes_under_suction=all(abs(row['cumulative_discharge_m3']) <= 1e-10
                                 for row in closed['outlet_history']),
        one_way_outlet=all(min(r['minimum_native_outlet_increment_m3'],
                              r['minimum_native_outlet_ledger_m3']) >= -1e-9
                           for r in [*runs.values(), closed]),
        water_balance=all(r['water_balance_max_residual_m3'] <= 1e-7
                          for r in [*runs.values(), closed]),
        temporal_discharge_sensitivity=temporal <= .05 * discharges[2],
    )
    config = json.loads((ROOT / 'config/engine.json').read_text())
    return dict(state='completed', passed=all(criteria.values()), criteria=criteria,
                scope='Native rectangular unsaturated soil grid with a lower right atmospheric outlet.',
                engine=config, engine_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                spatial_final_discharge_difference_m3=spatial,
                temporal_final_discharge_difference_m3=temporal,
                spatial_relative_final_discharge_difference=spatial/discharges[1] if discharges[1] else None,
                temporal_relative_final_discharge_difference=temporal/discharges[2] if discharges[2] else None,
                runs=runs, suction_control=closed)


def runoff_benchmark(folder):
    study = json.loads((ROOT / 'models/wetting_front_benchmark.json').read_text())
    spec = dict(study['column'], cells=8, output_interval_h=.025, surface_boundary='closed_ponding',
                duration_h=.25, rain_duration_h=.125, specific_storage_per_m=.03,
                initial_theta=.395)
    rates = [95, 0]
    routed = grid_trial(folder / 'routed', spec, rates, route_runoff=True)
    control = grid_trial(folder / 'closed-surface-control', spec, rates)
    runoff = routed['outlet_history'][-1]['cumulative_runoff_m3']
    control_runoff = control['outlet_history'][-1]['cumulative_runoff_m3']
    rainfall = .1 * cumulative_depth_m(dict(spec, rainfall_mm_h=rates[0]), spec['duration_h'])
    ponded = math.fsum(rows[-1]['surface_storage_m3'] for rows in routed['histories'])
    soil_gain = math.fsum(rows[-1]['water_storage_m3'] - rows[-1]['surface_storage_m3']
                         - rows[0]['water_storage_m3'] for rows in routed['histories'])
    criteria = dict(
        routed_runoff_exits=1e-5 < runoff < rainfall and abs(control_runoff) <= 1e-10,
        connected_dry_surface_receives_runon=max(
            row['surface_storage_m3'] for row in routed['histories'][1]) > 1e-7,
        water_balance=all(run['water_balance_max_residual_m3'] <= 1e-7 for run in (routed, control)),
        partition_closes=abs(rainfall - runoff - ponded - soil_gain) <= 1e-7,
    )
    return dict(state='completed', passed=all(criteria.values()), criteria=criteria,
                scope='Stock OHQ catchment routing across adjacent surfaces with prescribed routing slope.',
                spec=spec, routing_slope=.01, engine=json.loads((ROOT/'config/engine.json').read_text()),
                engine_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                rainfall_m3=rainfall, final_runoff_m3=runoff, final_surface_storage_m3=ponded,
                final_soil_storage_gain_m3=soil_gain, routed=routed, closed_surface_control=control)


def slope_benchmark(folder):
    study = json.loads((ROOT / 'models/wetting_front_benchmark.json').read_text())
    base = dict(study['column'], output_interval_h=.0125, surface_boundary='closed_ponding',
                duration_h=.125, rain_duration_h=.0625, specific_storage_per_m=.03,
                initial_theta=.399999)
    runs = {}
    for refinement, step_s in ((1, 15), (2, 15), (2, 7.5)):
        cells = [n * refinement for n in (8, 7, 6, 5) for _ in range(refinement)]
        spec = dict(base, cells=max(cells), solver_step_h=step_s/3600)
        name = f'{len(cells)}-columns-{step_s:g}s'
        run = grid_trial(folder / name, spec, [70] * (2*refinement) + [0] * (2*refinement),
                         width_m=.4, column_cells=cells, surface_slope=.375,
                         exposed_step_outlets=True, right_outlet_rows=range(cells[-1]),
                         route_runoff=True)
        run['probes'] = {
            'lower_face': sample_at_probe(run, .25, .13125),
            'toe': sample_at_probe(run, .35, .09375),
        }
        runs[name] = dict(spec=spec, **run)

    def compare(first, second):
        return {
            'max_probe_head_difference_m': {
                point: max(abs(a['pressure_head_m'] - b['pressure_head_m'])
                           for a, b in zip(history, second['probes'][point]))
                for point, history in first['probes'].items()
            },
            **{f'final_{q}_difference_m3': abs(first['outlet_history'][-1][f'cumulative_{q}_m3']
                                               - second['outlet_history'][-1][f'cumulative_{q}_m3'])
               for q in ('discharge', 'runoff')},
        }

    coarse, fine, half_step = runs.values()
    grid_difference, step_difference = compare(coarse, fine), compare(fine, half_step)
    final = half_step['outlet_history'][-1]
    applied = .2 * cumulative_depth_m(dict(base, rainfall_mm_h=70), base['duration_h'])
    initial = math.fsum(column[0]['water_storage_m3'] for column in half_step['histories'])
    total_end = math.fsum(column[-1]['water_storage_m3'] for column in half_step['histories'])
    surface_end = math.fsum(column[-1]['surface_storage_m3'] for column in half_step['histories'])
    partition = dict(rainfall_m3=applied, runoff_m3=final['cumulative_runoff_m3'],
                     seepage_m3=final['cumulative_discharge_m3'], surface_storage_m3=surface_end,
                     soil_storage_change_m3=total_end - initial - surface_end)
    criteria = dict(
        water_balance=all(run['water_balance_max_residual_m3'] <= 1e-7 for run in runs.values()),
        both_outlets_active=min(final['cumulative_discharge_m3'], final['cumulative_runoff_m3']) > 1e-6,
        one_way_seepage=all(run['minimum_native_outlet_increment_m3'] >= -1e-9 for run in runs.values()),
        temporal_pressure=max(step_difference['max_probe_head_difference_m'].values()) <= .02,
    )
    config = json.loads((ROOT/'config/engine.json').read_text())
    return dict(state='completed', passed=all(criteria.values()), criteria=criteria,
                engine=config, engine_binary_sha256=hashlib.sha256(BINARY.read_bytes()).hexdigest(),
                scope='Synthetic stepped slope with native OHQ soil, seepage and surface routing.',
                grid_difference=grid_difference, maximum_step_difference=step_difference,
                finest_partition=partition, runs=runs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/native-seepage-2d.json'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--outlet', action='store_true', help='Run native atmospheric outlet checks.')
    mode.add_argument('--runoff', action='store_true', help='Run native overland routing and infiltration checks.')
    mode.add_argument('--slope', action='store_true', help='Run the coupled synthetic stepped slope.')
    args = parser.parse_args()
    run = {'outlet': outlet_benchmark, 'runoff': runoff_benchmark, 'slope': slope_benchmark}
    selected = next((fn for name, fn in run.items() if getattr(args, name)), benchmark)

    result = selected(args.output.parent / (args.output.stem + '_files'))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Saved {args.output}: {'passed' if result['passed'] else 'failed'}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
