import unittest

from validation.geostudio_pressure_field import _weights


class GeoStudioPressureFieldTests(unittest.TestCase):
    def test_distorted_quad_reproduces_natural_coordinate_weights(self):
        points = [(0.,0.),(3.,.3),(2.6,2.),(-.15,1.4)]
        expected = (.48,.12,.08,.32)
        x = sum(point[0]*w for point,w in zip(points,expected,strict=True))
        y = sum(point[1]*w for point,w in zip(points,expected,strict=True))
        for actual,value in zip(_weights(points,x,y),expected,strict=True):
            self.assertAlmostEqual(actual,value,places=10)
        self.assertIsNone(_weights(points,3.,1.9))

    def test_triangle_interpolation_and_outside(self):
        points = [(0.,0.),(2.,0.),(0.,4.)]
        self.assertEqual(_weights(points,.5,1.),(.5,.25,.25))
        self.assertIsNone(_weights(points,1.5,2.))
