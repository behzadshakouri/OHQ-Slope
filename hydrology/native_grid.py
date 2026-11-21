"""Render and solve an elevation-aligned soil grid through native OHQ."""
from bisect import bisect_left, bisect_right
import hashlib
import math

from hydrology.column import (
    ENGINE, ROOT, initial_pressure, interpolate, native_settings, native_soil_block,
    run_engine, write_native_rainfall,
)
from hydrology.rainfall import cumulative_depth_m


def grid_trial(folder, spec, rain_rates_mm_h, *, link_columns=True, right_outlet_rows=(),
               route_runoff=False, width_m=.2, column_cells=None, surface_slope=.01,
               exposed_step_outlets=False, engine_seconds=120, cell_specs=None,
               rain_schedules=None, cancelled=lambda: False):
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
    if rain_schedules is not None:
        rain_specs = [dict(spec, rainfall_schedule=schedule) for schedule in rain_schedules]
    if cell_specs is None:
        cell_specs = [[spec] * count for count in column_cells]
    initial = {}
    soil_specs = {}
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
            material = cell_specs[i][j]
            soil_specs[soil] = material
            bottom = -(j+1)*dz if datum_at_surface else (count-j-1)*dz
            lines.append(native_soil_block(material, soil, dx, dz, bottom))
            initial[soil] = ('Storage', dx * dz * material['initial_theta'])
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
                     f"K_sat_original={soil_specs[f'Soil{i}_{j}']['ksat_m_day']}")

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
    raw = run_engine(folder, model, cancelled, wall_time_limit_s=engine_seconds+5)
    start_values = {f'storage_{obj}':value for obj, (_, value) in initial.items()}
    for obj, material in soil_specs.items():
        start_values[f'pressure_{obj}'] = initial_pressure(material)
        start_values[f'theta_{obj}'] = material['initial_theta']
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

    initial_water = [dx * dz * math.fsum(material['initial_theta'] for material in column)
                     for column in cell_specs]
    residual = max(abs(discharge(time) + runoff(time) + excess(time) + math.fsum(
        storage(i, time) - initial_water[i] - dx * cumulative_depth_m(rain, time)
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
                rainfall_mm_h=rain_rates_mm_h, rainfall_schedules=rain_schedules, connected=link_columns, outlet_rows=list(right_outlet_rows),
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


def sample_at_probe(run, x_m, elevation_m, *, include_boundary_cells=False):
    """Interpolate between centres, with optional constant half-cell boundary extension."""
    edges = run['x_edges_m']
    heights = run['surface_elevation_m']
    dz = run['cell_height_m']
    centers = [(a + b)/2 for a, b in zip(edges, edges[1:])]
    i = bisect_left(centers, x_m - 1e-10)
    if i < len(centers) and abs(centers[i] - x_m) <= 1e-10:
        columns = [i]
    elif 0 < i < len(centers):
        columns = [i-1, i]
    elif include_boundary_cells and edges[0] <= x_m <= edges[-1]:
        columns = [0 if i == 0 else len(centers)-1]
    else:
        raise ValueError('Probe is outside the horizontal cell-centre bounds.')

    if include_boundary_cells:
        owner = min(len(centers)-1,bisect_right(edges,x_m)-1)
        floor = heights[owner]-run['column_cells'][owner]*dz
        if (not edges[0] <= x_m <= edges[-1]
                or not floor-1e-10 <= elevation_m <= heights[owner]+1e-10):
            raise ValueError('Probe is outside the soil domain.')
        # A step can put the neighbouring column outside the soil at this elevation.
        if any(elevation_m > heights[j]+1e-10 or
               elevation_m < heights[j]-run['column_cells'][j]*dz-1e-10 for j in columns):
            columns = [owner]

    def sample(series, target):
        if include_boundary_cells:
            target = max(series[0][0],min(series[-1][0],target))
        return interpolate(series,target)

    samples = []
    for rows in zip(*(run['histories'][i] for i in columns)):
        values = []
        for i, row in zip(columns, rows):
            pressure_by_z = [(heights[i] - (j+.5)*dz, pressure)
                             for j, pressure in enumerate(row['pressure_head_m'])]
            values.append(sample(list(reversed(pressure_by_z)), elevation_m))
        samples.append({'time_h':rows[0]['time_h'],
                        'pressure_head_m':sample([(centers[j],v) for j,v in zip(columns,values)],x_m)})
    return samples
