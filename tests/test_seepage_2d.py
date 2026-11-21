import unittest

from hydrology.seepage_2d import Grid, steady_seepage, transient_step
from validation.seepage_2d import benchmark, transient_benchmark


class Seepage2DTests(unittest.TestCase):
    def test_steady_lateral_flow_and_1d_limit(self):
        result = benchmark()
        self.assertTrue(result['passed'], result['criteria'])

    def test_rainfall_and_one_way_outlet(self):
        result = transient_benchmark()
        self.assertTrue(result['passed'], result['criteria'])

    def test_conductivity_direction_and_closed_faces(self):
        grid = Grid(2., 1., 4, 3)
        result = steady_seepage(grid, .05, .01, {'left': [2.] * 3, 'right': [1.] * 3})
        for row in result['darcy_flux_x_m_h']:
            for value in row:
                self.assertAlmostEqual(value, .025)
        self.assertAlmostEqual(result['boundary_outflow_m3_h']['right'], .025)
        self.assertAlmostEqual(result['boundary_outflow_m3_h']['bottom'], 0.)

    def test_invalid_inputs_and_unsaturated_state_are_rejected(self):
        grid = Grid(1., 1., 1, 1)
        with self.assertRaises(ValueError):
            steady_seepage(grid, .1, .1, {})
        with self.assertRaises(ValueError):
            steady_seepage(grid, .1, .1, {'top': [1., 2.]})
        with self.assertRaisesRegex(ValueError, 'nonnegative'):
            transient_step(grid, .1, .1, [[.4]], .2, .05, .02, [0])


if __name__ == '__main__':
    unittest.main()
