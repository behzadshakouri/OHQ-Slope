from dataclasses import replace
import math
import unittest

from hydrology.native_grid import sample_at_probe
from stability.bishop import Slice, factor_of_safety
from stability.section import circular_slices, fixed_surface_history


class FixedSlipTests(unittest.TestCase):
    def test_independent_bishop_closed_form_and_suction(self):
        angle = math.radians(25)
        phi = math.radians(30)
        phi_b = math.radians(10)
        part = Slice(2.,30.,angle,4.,phi,-3.,phi_b)
        for pressure in (-3.,0.,2.):
            c = part.cohesion_kpa+max(0.,-pressure)*math.tan(phi_b)
            expected = (2*c+(30*math.cos(angle)**2-2*max(0.,pressure))*math.tan(phi))/(
                30*math.sin(angle)*math.cos(angle))
            self.assertAlmostEqual(factor_of_safety([replace(part,pressure_kpa=pressure)]),expected)
        with self.assertRaisesRegex(ValueError,'driving'):
            factor_of_safety([replace(part,downslope_angle_rad=-angle)])

    def test_slices_follow_a_circular_base(self):
        parts, points = circular_slices([(0.,2.),(2.,1.)],0.,2.,.25,20,12.,4.,.5)
        self.assertEqual(len(parts),20)
        self.assertTrue(all(part.weight_kn_m > 0 for part in parts))
        chord = math.hypot(2.,1.)
        radius = chord**2/(8*.25)+.25/2
        distance = radius-.25
        cx,cy = 1+distance/chord,1.5+2*distance/chord
        for x,y in points:
            self.assertAlmostEqual(math.hypot(x-cx,y-cy),radius)
        self.assertGreater(factor_of_safety(parts),0.)

    def test_fixed_slip_pressure_transfer_at_step_and_boundary(self):
        def frame(time,heads):
            return {'time_h':time,'pressure_head_m':heads}
        run = {'x_edges_m':[0.,1.,2.],'surface_elevation_m':[2.,1.],'column_cells':[2,1],
               'cell_height_m':1.,'histories':[[frame(0.,[-1.,-3.]),frame(1.,[.2,.4])],
                                               [frame(0.,[-2.]),frame(1.,[.6])]]}
        self.assertEqual(sample_at_probe(run,.9,1.7,include_boundary_cells=True)[0]['pressure_head_m'],-1.)
        self.assertAlmostEqual(sample_at_probe(run,1.,.5,include_boundary_cells=True)[0]['pressure_head_m'],-2.5)
        with self.assertRaisesRegex(ValueError,'soil domain'):
            sample_at_probe(run,1.1,1.7,include_boundary_cells=True)
        parts = [Slice(.5,30.,.4,4.,.5,0.,.2),Slice(.5,20.,-.1,4.,.5,0.,.2)]
        history = fixed_surface_history(run,parts,[(.1,1.8),(1.9,.9)],10.)
        self.assertEqual(history[0]['pressure_kpa'],[-10.,-20.])
        self.assertEqual(history[1]['pressure_kpa'],[2.,6.])
        self.assertGreater(history[0]['factor_of_safety'],history[1]['factor_of_safety'])


if __name__ == '__main__':
    unittest.main()
