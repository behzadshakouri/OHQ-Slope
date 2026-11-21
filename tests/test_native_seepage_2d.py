from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hydrology.column import DEFAULT, ready
from validation.native_seepage_2d import benchmark, grid_trial, outlet_benchmark, runoff_benchmark


@unittest.skipUnless(ready(), 'Build the pinned console for native grid tests.')
class NativeSeepage2DTests(unittest.TestCase):
    def test_native_uniform_and_localized_rainfall(self):
        with TemporaryDirectory() as folder:
            result = benchmark(Path(folder))
        self.assertTrue(result['passed'], result['criteria'])

    def test_native_outlet_discharge_and_suction_control(self):
        with TemporaryDirectory() as folder:
            result = outlet_benchmark(Path(folder))
        self.assertTrue(result['passed'], result['criteria'])

    def test_stock_catchment_routing_partitions_rainfall(self):
        with TemporaryDirectory() as folder:
            result = runoff_benchmark(Path(folder))
        self.assertTrue(result['passed'], result['criteria'])

    def test_reviewed_rainfall_uses_actual_cell_area(self):
        spec = dict(DEFAULT, depth_m=.1, cells=2, initial_theta=.39, ksat_m_day=.1,
                    rain_duration_h=.125, duration_h=.25, output_interval_h=.05,
                    solver_step_h=1/480, surface_boundary='reviewed_infiltration',
                    formulation='cell_centred')
        with TemporaryDirectory() as folder:
            result = grid_trial(Path(folder), spec, [100., 100.])
        self.assertLess(result['water_balance_max_residual_m3'], 1e-10)
        self.assertGreater(result['outlet_history'][-1]['cumulative_surface_excess_m3'], .002)
        self.assertLessEqual(max(abs(row['surface_storage_m3']) for column in result['histories']
                                 for row in column), 1e-10)


if __name__ == '__main__':
    unittest.main()
