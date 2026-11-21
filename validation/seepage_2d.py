"""Verify 2D saturated lateral flow against a separable analytical head field."""
import argparse
import json
import math
from pathlib import Path

from hydrology.seepage_2d import Grid, steady_seepage, transient_step


def check(grid, amplitude_m):
    kx, kz = .035, .018
    base, gradient = 1.2, .35
    wave = math.pi / grid.width_m
    decay = wave * math.sqrt(kx / kz)
    scale = math.sinh(decay * grid.height_m)

    def head(x, z):
        return base + gradient * z + amplitude_m * math.cos(wave * x) * math.sinh(decay * z) / scale

    def qx(x, z):
        return kx * amplitude_m * wave * math.sin(wave * x) * math.sinh(decay * z) / scale

    def qz(x, z):
        return -kz * (gradient + amplitude_m * decay * math.cos(wave * x)
                      * math.cosh(decay * z) / scale)

    centers = [(i + .5) * grid.dx for i in range(grid.nx)]
    solution = steady_seepage(grid, kx, kz, {
        'bottom': [head(x, 0) for x in centers],
        'top': [head(x, grid.height_m) for x in centers],
    })
    x, z = solution['x_m'], solution['z_m']
    error_x = max(abs(row[i] - qx(i * grid.dx, height))
                  for height, row in zip(z, solution['darcy_flux_x_m_h'])
                  for i in range(grid.nx + 1))
    error_z = max(abs(value - qz(position, j * grid.dz))
                  for j in range(1, grid.nz)
                  for position, value in zip(x, solution['darcy_flux_z_m_h'][j]))
    error_boundary = max(abs(value - qz(position, j * grid.dz))
                         for j in (0, grid.nz)
                         for position, value in zip(x, solution['darcy_flux_z_m_h'][j]))
    head_error = max(abs(value - head(position, height))
                     for height, row in zip(z, solution['total_head_m'])
                     for position, value in zip(x, row))
    exact_throughflow = kz * gradient * grid.width_m
    throughflow_error = max(abs(solution['boundary_outflow_m3_h'][side] - target)
                            for side, target in (('bottom', exact_throughflow), ('top', -exact_throughflow)))
    metrics = dict(max_head_error_m=head_error, max_x_flux_error_m_h=error_x,
                   max_interior_z_flux_error_m_h=error_z,
                   max_boundary_z_flux_error_m_h=error_boundary,
                   max_integrated_throughflow_error_m3_h=throughflow_error,
                   peak_lateral_flux_m_h=max(abs(v) for row in solution['darcy_flux_x_m_h'] for v in row),
                   net_boundary_outflow_m3_h=solution['net_boundary_outflow_m3_h'],
                   max_cell_balance_residual_m3_h=solution['max_cell_balance_residual_m3_h'])
    return metrics, solution


def benchmark():
    grids = [Grid(2., 1., n, n // 2) for n in (16, 32, 64)]
    runs = []
    for grid in grids:
        metrics, field = check(grid, .25)
        runs.append(dict(nx=grid.nx, nz=grid.nz, **metrics))
    one_d, _ = check(grids[0], 0.)
    limits = dict(max_head_error_m=2e-4, max_x_flux_error_m_h=5e-5,
                  max_interior_z_flux_error_m_h=5e-5, max_boundary_z_flux_error_m_h=3e-4)
    balance_limit = 1e-9
    criteria = {
        'finest_grid_accuracy': all(runs[-1][name] <= limit for name, limit in limits.items()),
        'grid_refinement_reduces_error': all(b[name] < a[name] for name in limits
                                             for a, b in zip(runs, runs[1:])),
        'nonzero_lateral_flow': runs[-1]['peak_lateral_flux_m_h'] > .005,
        'integrated_throughflow': all(run['max_integrated_throughflow_error_m3_h'] <= balance_limit
                                     for run in runs),
        'water_balance': all(abs(run['net_boundary_outflow_m3_h']) <= balance_limit
                             and run['max_cell_balance_residual_m3_h'] <= balance_limit
                             for run in [*runs, one_d]),
        'one_dimensional_limit': all(one_d[name] <= 1e-9 for name in
                                     ('max_head_error_m', 'peak_lateral_flux_m_h',
                                      'max_interior_z_flux_error_m_h', 'max_boundary_z_flux_error_m_h',
                                      'max_integrated_throughflow_error_m3_h')),
    }
    return dict(state='completed', passed=all(criteria.values()), criteria=criteria, limits=limits,
                balance_limit_m3_h=balance_limit, runs=runs, one_dimensional_limit=one_d,
                finest_field=field, domain_m=[2., 1.], conductivity_m_h=[.035, .018],
                head_base_m=1.2, vertical_gradient=.35, lateral_amplitude_m=.25,
                scope='Steady saturated rectangular finite-volume benchmark with unit out-of-plane width.')


def rainfall_pulse(grid, step_h):
    initial_head, storage = 1.4, .3
    duration, rain_end, rain_rate = .125, .0625, .035
    previous = [[initial_head] * grid.nx for _ in range(grid.nz)]
    candidates = range(grid.nz // 2, grid.nz)
    history = []
    cumulative_discharge = cumulative_storage = cumulative_rainfall = 0.
    for i in range(round(duration / step_h)):
        time = (i + 1) * step_h
        rain = rain_rate if i * step_h < rain_end else 0.
        result = transient_step(grid, .035, .018, previous, storage, step_h, rain, candidates)
        previous = result['total_head_m']
        discharge = result['boundary_outflow_m3_h']['right']
        cumulative_rainfall += rain * grid.width_m * step_h
        cumulative_discharge += discharge * step_h
        cumulative_storage += result['storage_change_m3_h'] * step_h
        history.append(dict(time_h=time, rainfall_m_h=rain, seepage_outflow_m3_h=discharge,
                            storage_change_m3_h=result['storage_change_m3_h'],
                            active_faces=result['active_right_seepage_faces'],
                            minimum_pressure_head_m=min(map(min, result['pressure_head_m'])),
                            max_cell_balance_residual_m3_h=result['max_cell_balance_residual_m3_h'],
                            cumulative_residual_m3=cumulative_storage + cumulative_discharge - cumulative_rainfall))
    return dict(step_h=step_h, history=history, final_field=result,
                cumulative_discharge_m3=cumulative_discharge,
                cumulative_storage_change_m3=cumulative_storage,
                cumulative_rainfall_m3=cumulative_rainfall)


def transient_benchmark():
    grid = Grid(2., 1., 24, 12)
    runs = [rainfall_pulse(grid, 1 / n) for n in (128, 256, 512)]
    rows = [row for run in runs for row in run['history']]
    differences = [
        max(abs(x - y) for a, b in zip(first['final_field']['total_head_m'],
                                       second['final_field']['total_head_m'])
            for x, y in zip(a, b))
        for first, second in zip(runs, runs[1:])
    ]
    # With a single cell a closed outlet at zero gauge pressure opens when
    # applied rainfall raises the cell head above the outlet elevation.
    cell = Grid(1., 1., 1, 1)
    dry = transient_step(cell, .1, .1, [[.5]], .2, .05, 0., [0])
    wet = transient_step(cell, .1, .1, [[.5]], .2, .05, .02, [0])
    expected_increment = .02 / (.2 / .05 + .1 / .5)
    criteria = dict(
        analytical_activation=(dry['active_right_seepage_faces'] == []
                               and wet['active_right_seepage_faces'] == [0]
                               and abs(wet['total_head_m'][0][0] - .5 - expected_increment) < 1e-12),
        one_way_discharge=all(row['seepage_outflow_m3_h'] >= 0 for row in rows)
                          and all(run['cumulative_discharge_m3'] > 0 for run in runs),
        saturated_pressures=min(row['minimum_pressure_head_m'] for row in rows) >= 0,
        rainfall_balance=all(abs(run['cumulative_rainfall_m3'] - .035 * .0625 * 2.) < 1e-12
                             for run in runs),
        water_balance=max(abs(row['cumulative_residual_m3']) for row in rows) <= 1e-9
                      and max(row['max_cell_balance_residual_m3_h'] for row in rows) <= 1e-9,
        temporal_refinement=differences[1] < differences[0] and differences[1] <= .01,
    )
    return dict(state='completed', passed=all(criteria.values()), criteria=criteria, runs=runs,
                max_final_head_step_differences_m=differences, cells=[grid.nx, grid.nz],
                domain_m=[grid.width_m, grid.height_m], conductivity_m_h=[.035, .018],
                initial_total_head_m=1.4, specific_storage_per_m=.3, rain_duration_h=.0625,
                rain_intensity_m_h=.035,
                analytical_opening_head_increment_m=expected_increment,
                scope='Saturated transient reference with imposed infiltration and a one-way atmospheric right outlet.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('results/seepage-2d.json'))
    parser.add_argument('--transient', action='store_true', help='Run the saturated rainfall and outlet case.')
    args = parser.parse_args()
    result = transient_benchmark() if args.transient else benchmark()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Saved {args.output}: {'passed' if result['passed'] else 'failed'}")
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
