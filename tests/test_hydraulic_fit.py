import csv
import math
import os
from pathlib import Path
import tempfile
import unittest

from hydrology.column import DEFAULT
from validation.hydraulic_fit import curves, predict, fit
from validation.ponding import retention


class HydraulicFitTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OHQ_FIT_OPTIMIZER_TEST')=='1',
                         'Optional SciPy optimizer check; set OHQ_FIT_OPTIMIZER_TEST=1.')
    def test_joint_optimizer_recovers_known_parameters(self):
        p={**DEFAULT,'theta_res':.03,'theta_sat':.35,'alpha_per_m':4.,'n':2.7,
           'ksat_m_day':.2,'pore_connectivity':.6}
        data={name:[] for name in ('retention','conductivity')}
        for suction in [0]+[10**(-2+i*3.3/19) for i in range(20)]:
            theta,k,valid=predict(suction,p)
            self.assertTrue(valid)
            data['retention'].append((suction,theta));data['conductivity'].append((suction,k))
        result=fit(data,starts=4)
        self.assertTrue(result['optimizer_success'])
        self.assertLess(result['metrics']['retention']['rmse'],1e-9)
        self.assertLess(result['metrics']['conductivity']['log10_rmse'],1e-8)
        for name in result['fitted_parameters']:
            self.assertTrue(math.isclose(result['parameters'][name],p[name],rel_tol=1e-6),name)

    def test_forward_law_matches_independent_storage_on_both_branches(self):
        # Includes zero pressure in the compressible branch and unsaturated states.
        for head in (0, -.001, -.1, -1, -10):
            with self.subTest(head=head):
                theta, _, k = retention(head, DEFAULT)
                actual_theta, actual_k, valid = predict(-head*9.807, DEFAULT)
                self.assertTrue(valid)
                self.assertAlmostEqual(actual_theta, theta, places=13)
                self.assertAlmostEqual(actual_k*86400, k, places=13)

    def test_dry_floor_is_flagged_instead_of_claiming_invertible_pressure(self):
        theta,k,valid=predict(1e8, DEFAULT)
        self.assertFalse(valid)
        self.assertAlmostEqual(theta, DEFAULT['theta_res']+.001*(DEFAULT['theta_sat']-DEFAULT['theta_res']))
        self.assertTrue(math.isfinite(k) and k>0)

    def test_csv_units_order_and_monotonicity_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'curves.csv'
            def write(change=None):
                with p.open('w',newline='') as f:
                    writer=csv.writer(f);writer.writerow(['function','pressure_magnitude_kPa','value','value_unit'])
                    for name,unit in [('retention','m3/m3'),('conductivity','m/s')]:
                        for i in range(5):
                            row=[name,i,.4/(i+1),unit]
                            if change and name=='retention' and i==4:change(row)
                            writer.writerow(row)
            write();self.assertEqual(len(curves(p)['retention']),5)
            for change in (lambda r:r.__setitem__(3,'percent'),lambda r:r.__setitem__(1,0),
                           lambda r:r.__setitem__(2,float('nan')),lambda r:r.__setitem__(2,.9)):
                write(change)
                with self.assertRaises(ValueError):curves(p)


if __name__=='__main__':unittest.main()
