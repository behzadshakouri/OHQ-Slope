"""Check a native OHQ soil grid under uniform and localized rainfall."""
import argparse
import hashlib
import json
import math
from pathlib import Path

from hydrology.column import (
    BINARY, ENGINE, ROOT, initial_pressure, interpolate, native_settings, native_soil_block,
    run_engine, simulate, write_native_rainfall,
)
from hydrology.rainfall import cumulative_depth_m


def grid_trial(folder, spec, rain_rates_mm_h, *, link_columns=True):
    width_m = .2
    dx = width_m / len(rain_rates_mm_h)
    dz = spec['depth_m'] / spec['cells']
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    lines = [
        f'loadtemplate;filename={ENGINE}/resources/main_components.json',
        f'addtemplate;filename={ENGINE}/resources/unsaturated_soil.json',
        f'addtemplate;filename={ROOT}/components/cell_centred_column.json',
    ]
    rain_specs = [dict(spec, rainfall_mm_h=rate) for rate in rain_rates_mm_h]
    initial = {}
    for i, rain in enumerate(rain_specs):
        write_native_rainfall(folder, rain, f'rain_{i}.csv')
        lines.extend([
            f'create source;type=Precipitation,name=Rain{i},timeseries=rain_{i}.csv',
            f'create block;type=Catchment,name=Surface{i},area={dx},depth=0,elevation=0,'
            f'Slope=0.01,Width=1,ManningCoeff=0.03,depression_storage=0,'
            f'Runoff_coeff=1,loss_coefficient=0,Precipitation=Rain{i}',
        ])
        initial[f'Surface{i}'] = ('Storage', 0.)
        for j in range(spec['cells']):
            soil = f'Soil{i}_{j}'
            lines.append(native_soil_block(spec, soil, dx, dz, -(j + 1) * dz))
            initial[soil] = ('Storage', dx * dz * spec['initial_theta'])
            if j:
                lines.append(f'create link;type=Column Centre Soil Link,from=Soil{i}_{j-1},'
                             f'to={soil},name=Vertical{i}_{j}')
            if i and link_columns:
                lines.append(f'create link;type=soil_to_soil_H_link,from=Soil{i-1}_{j},'
                             f'to={soil},name=Lateral{i}_{j},length={dx},area={dz}')

        lines.append(f'create link;type=Column Centre Surface Link,from=Surface{i},to=Soil{i}_0,'
                     f'name=Infiltration{i}')

    def observe(name, obj, quantity):
        lines.append(f'create observation;type=Observation,name={name},object={obj},'
                     f'expression={quantity},observed_data=,error_structure=normal,'
                     'error_standard_deviation=1')

    for obj, (quantity, _) in initial.items():
        observe(f'storage_{obj}', obj, quantity)
        if obj.startswith('Soil'):
            observe(f'pressure_{obj}', obj, 'pressure_head')
            observe(f'theta_{obj}', obj, 'theta')
    lines.extend(native_settings(spec, centred=True))
    model = folder / 'section.ohq'
    model.write_text('\n'.join(lines) + '\n')
    raw = run_engine(folder, model)
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
        cells = (f'storage_Soil{i}_{j}' for j in range(spec['cells']))
        return math.fsum(interpolate(raw[name], time)
                         for name in (f'storage_Surface{i}', *cells))

    residual = max(abs(math.fsum(storage(i, time) - dx * (
        spec['depth_m'] * spec['initial_theta'] + cumulative_depth_m(rain, time))
        for i, rain in enumerate(rain_specs))) for time, _ in raw['storage_Surface0'])
    times = [min(i * spec['output_interval_h'], spec['duration_h'])
             for i in range(round(spec['duration_h'] / spec['output_interval_h']) + 1)]
    histories = [
        [dict(time_h=time, water_storage_m3=storage(i, time),
              pressure_head_m=[interpolate(raw[f'pressure_Soil{i}_{j}'], time)
                               for j in range(spec['cells'])],
              theta=[interpolate(raw[f'theta_Soil{i}_{j}'], time)
                     for j in range(spec['cells'])])
         for time in times]
        for i in range(len(rain_rates_mm_h))
    ]
    return dict(histories=histories, water_balance_max_residual_m3=residual,
                rainfall_mm_h=rain_rates_mm_h, connected=link_columns,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/native-seepage-2d.json'))
    args = parser.parse_args()
    result = benchmark(args.output.parent / (args.output.stem + '_files'))
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Saved {args.output}: {'passed' if result['passed'] else 'failed'}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
