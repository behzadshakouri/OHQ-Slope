"""Check a native OHQ soil grid under uniform and localized rainfall."""
import argparse
from bisect import bisect_left
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import (
    BINARY, ENGINE, ROOT, initial_pressure, interpolate, native_settings, native_soil_block,
    run_engine, simulate, write_native_rainfall,
)
from hydrology.rainfall import cumulative_depth_m


def grid_trial(folder, spec, rain_rates_mm_h, *, link_columns=True, right_outlet_rows=(),
               route_runoff=False, width_m=.2, column_cells=None, surface_slope=.01,
               exposed_step_outlets=False, engine_seconds=120):
    if type(engine_seconds) is not int or not 1 <= engine_seconds <= 900:
        raise ValueError('Native engine budget must be 1–900 seconds.')
    reviewed = spec.get('surface_boundary') == 'reviewed_infiltration'
    if reviewed and route_runoff:
        raise ValueError('Use either reviewed drainage or connected surface runoff.')
    datum_at_surface = column_cells is None
    if column_cells is None:
        column_cells = [spec['cells']] * len(rain_rates_mm_h)
    if (len(column_cells) != len(rain_rates_mm_h)
            or any(type(n) is not int or not 1 <= n <= spec['cells'] for n in column_cells)
            or any(right > left for left, right in zip(column_cells, column_cells[1:]))):
        raise ValueError('Column cell counts must match the rainfall cells and descend toward the toe.')
    dx = width_m / len(rain_rates_mm_h)
    dz = spec['depth_m'] / spec['cells']
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        f'loadtemplate;filename={ENGINE}/resources/main_components.json',
        f'addtemplate;filename={ENGINE}/resources/unsaturated_soil.json',
        f'addtemplate;filename={ROOT}/components/cell_centred_column.json',
    ]
    datum_shift = -spec['depth_m'] if datum_at_surface else 0.
    if reviewed:
        lines.append(f'addtemplate;filename={ROOT}/components/reviewed_surface.json')
    rain_specs = [dict(spec, rainfall_mm_h=rate) for rate in rain_rates_mm_h]
    initial = {}
    for i, (rain, count) in enumerate(zip(rain_specs, column_cells)):
        write_native_rainfall(folder, rain, f'rain_{i}.csv')
        lines.extend([
            f'create source;type=Precipitation,name=Rain{i},timeseries=rain_{i}.csv',
            f'create block;type=Catchment,name=Surface{i},area={dx},depth=0,elevation={datum_shift + count*dz},'
            f'Slope={surface_slope},Width=1,ManningCoeff=0.03,depression_storage=0,'
            f'Runoff_coeff=1,loss_coefficient=0,Precipitation=Rain{i}',
        ])
        initial[f'Surface{i}'] = ('Storage', 0.)
        for j in range(count):
            soil = f'Soil{i}_{j}'
            lines.append(native_soil_block(spec, soil, dx, dz, -(j + 1)*dz if datum_at_surface else (count - j - 1)*dz))
            initial[soil] = ('Storage', dx * dz * spec['initial_theta'])
            if j:
                lines.append(f'create link;type=Column Centre Soil Link,from=Soil{i}_{j-1},'
                             f'to={soil},name=Vertical{i}_{j}')
            if i and link_columns:
                left_j = j + column_cells[i-1] - count
                lines.append(f'create link;type=soil_to_soil_H_link,from=Soil{i-1}_{left_j},'
                             f'to={soil},name=Lateral{i}_{j},length={dx},area={dz}')

        if reviewed:
            collector = f'Excess{i}'
            lines.extend([
                f'create block;type=Column Reviewed Excess Collector,name={collector},area={dx},Precipitation=Rain{i}',
                f'create link;type=Column Reviewed Rain Link,from=Surface{i},to=Soil{i}_0,name=Infiltration{i}',
                f'create link;type=Column Reviewed Excess Link,from=Soil{i}_0,to={collector},name=Reject{i}',
            ])
            initial[collector] = ('Storage', 0.)
        else:
            lines.append(f'create link;type=Column Centre Surface Link,from=Surface{i},to=Soil{i}_0,'
                         f'name=Infiltration{i}')

    outlet_cells = [(len(column_cells) - 1, j) for j in right_outlet_rows]
    if exposed_step_outlets:
        outlet_cells.extend((i, j) for i, (left, right) in
                            enumerate(zip(column_cells, column_cells[1:]))
                            for j in range(left - right))
    if outlet_cells or route_runoff:
        lines.insert(3, f'addtemplate;filename={ROOT}/components/column_boundaries.json')
    outlets = []
    for i, j in outlet_cells:
        outlet = f'Outlet{i}_{j}'
        outlets.append(outlet)
        initial[outlet] = ('Storage', 0.)
        lines.append(f'create block;type=Column Drainage Collector,name={outlet}')
        lines.append(f'create link;type=soil_free_outflow,from=Soil{i}_{j},to={outlet},'
                     f'name=Seepage{i}_{j},length={dx/2},area={dz},'
                     f"K_sat_original={spec['ksat_m_day']}")

    if route_runoff:
        lines.append('create block;type=Column Drainage Collector,name=RunoffOutlet')
        initial['RunoffOutlet'] = ('Storage', 0.)
        for i in range(len(rain_rates_mm_h)):
            target = f'Surface{i+1}' if i + 1 < len(rain_rates_mm_h) else 'RunoffOutlet'
            lines.append(f'create link;type=Catchment_link,from=Surface{i},to={target},'
                         f'name=RunoffRoute{i}')

    def observe(name, obj, quantity):
        lines.append(f'create observation;type=Observation,name={name},object={obj},'
                     f'expression={quantity},observed_data=,error_structure=normal,'
                     'error_standard_deviation=1')

    for obj, (quantity, _) in initial.items():
        observe(f'storage_{obj}', obj, quantity)
        if obj.startswith('Soil'):
            observe(f'pressure_{obj}', obj, 'pressure_head')
            observe(f'theta_{obj}', obj, 'theta')
    lines.extend(line.replace('quantity=maximum_time_allowed,value=120',
                              f'quantity=maximum_time_allowed,value={engine_seconds}')
                 for line in native_settings(spec, centred=True, reviewed=reviewed))
    model = folder / 'section.ohq'
    model.write_text('\n'.join(lines) + '\n')
    raw = run_engine(folder, model, wall_time_limit_s=engine_seconds+5)
    start_values = {f'storage_{obj}':value for obj, (_, value) in initial.items()}
    for obj in initial:
        if obj.startswith('Soil'):
            start_values[f'pressure_{obj}'] = initial_pressure(spec)
            start_values[f'theta_{obj}'] = spec['initial_theta']
    if set(raw) != set(start_values):
        raise ValueError('Unexpected native grid observation names.')
    placeholders = all(abs(series[0][1]) < 1e-14 for series in raw.values())
    for name, value in start_values.items():
        time, reported = raw[name][0]
        if abs(time) > 1e-10 or (not placeholders and abs(reported - value) > 1e-8):
            raise ValueError(f'Invalid native initial observation for {name}.')
        raw[name][0] = (0., value)

    def storage(i, time):
        cells = (f'storage_Soil{i}_{j}' for j in range(column_cells[i]))
        return math.fsum(interpolate(raw[name], time)
                         for name in (f'storage_Surface{i}', *cells))

    outlet_series = [raw[f'storage_{name}'] for name in outlets]

    def discharge(time):
        return math.fsum(interpolate(series, time) for series in outlet_series)

    def runoff(time):
        return interpolate(raw['storage_RunoffOutlet'], time) if route_runoff else 0.

    excess_series = [raw[f'storage_Excess{i}'] for i in range(len(column_cells))] if reviewed else []

    def excess(time):
        return math.fsum(interpolate(series, time) for series in excess_series)

    residual = max(abs(discharge(time) + runoff(time) + excess(time) + math.fsum(
        storage(i, time) - dx * (column_cells[i] * dz * spec['initial_theta'] + cumulative_depth_m(rain, time))
        for i, rain in enumerate(rain_specs))) for time, _ in raw['storage_Surface0'])
    duration = spec['duration_h']
    spacing = spec['output_interval_h']
    times = [i * spacing for i in range(int(duration / spacing) + 1)]
    if abs(times[-1] - duration) > 1e-8:
        times.append(duration)
    histories = [
        [dict(time_h=time, water_storage_m3=storage(i, time),
              surface_storage_m3=interpolate(raw[f'storage_Surface{i}'], time),
              pressure_head_m=[interpolate(raw[f'pressure_Soil{i}_{j}'], time)
                               for j in range(column_cells[i])],
              theta=[interpolate(raw[f'theta_Soil{i}_{j}'], time)
                     for j in range(column_cells[i])])
         for time in times]
        for i in range(len(rain_rates_mm_h))
    ]
    return dict(histories=histories, water_balance_max_residual_m3=residual,
                rainfall_mm_h=rain_rates_mm_h, connected=link_columns, outlet_rows=list(right_outlet_rows),
                outlet_history=[dict(time_h=time, cumulative_discharge_m3=discharge(time),
                                     cumulative_runoff_m3=runoff(time),
                                     cumulative_surface_excess_m3=excess(time)) for time in times],
                reviewed_surface=reviewed, engine_limit_s=engine_seconds,
                minimum_native_excess_increment_m3=min(
                    (b[1]-a[1] for series in excess_series for a, b in zip(series, series[1:])), default=0.),
                routed_runoff=route_runoff, outlet_cells=outlet_cells, column_cells=column_cells,
                x_edges_m=[i * dx for i in range(len(column_cells) + 1)], cell_height_m=dz,
                surface_elevation_m=[datum_shift + count * dz for count in column_cells],
                routing_slope=surface_slope,
                minimum_native_outlet_increment_m3=min(
                    (b[1] - a[1] for series in outlet_series for a, b in zip(series, series[1:])), default=0.),
                minimum_native_outlet_ledger_m3=min(
                    (value for series in outlet_series for _, value in series), default=0.),
                model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())


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


def sample_at_probe(run, x_m, elevation_m):
    """Sample pressure at a physical probe bracketed by wet-domain cell centres."""
    edges = run['x_edges_m']
    heights = run['surface_elevation_m']
    dz = run['cell_height_m']
    all_centers = [(a + b)/2 for a, b in zip(edges, edges[1:])]
    i = bisect_left(all_centers, x_m - 1e-10)
    if i < len(all_centers) and abs(all_centers[i] - x_m) <= 1e-10:
        columns = [i]
    elif 0 < i < len(all_centers):
        columns = [i-1, i]
    else:
        raise ValueError('Probe is outside the horizontal cell-centre bounds.')
    centers = [all_centers[j] for j in columns]
    samples = []
    for rows in zip(*(run['histories'][i] for i in columns)):
        values = []
        for i, row in zip(columns, rows):
            pressure_by_z = [(heights[i] - (j + .5)*dz, pressure)
                             for j, pressure in enumerate(row['pressure_head_m'])]
            values.append(interpolate(list(reversed(pressure_by_z)), elevation_m))
        samples.append({'time_h': rows[0]['time_h'],
                        'pressure_head_m': interpolate(list(zip(centers, values)), x_m)})
    return samples


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
