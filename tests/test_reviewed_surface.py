from pathlib import Path
import json
import tempfile
import unittest

from hydrology.column import DEFAULT, ROOT, ready, simulate, validate_column
from validation.ponding import reference, retention

SPEC={**DEFAULT,'formulation':'cell_centred','surface_boundary':'reviewed_infiltration',
      'depth_m':.1,'cells':4,'rainfall_mm_h':100.,'rain_duration_h':.5,'duration_h':1.,
      'output_interval_h':.05,'solver_step_h':1/480,'ksat_m_day':.1,'initial_theta':.39}


class ReviewedValidationTests(unittest.TestCase):
    def test_explicit_selection_and_reject_unsupported_formulation(self):
        self.assertEqual(validate_column(SPEC,.05)['surface_boundary'],'reviewed_infiltration')
        for change in ({'surface_boundary':'unknown'},{'formulation':'legacy_top'}):
            with self.assertRaises(ValueError):validate_column({**SPEC,**change},.05)
        self.assertNotIn('surface_boundary',validate_column(DEFAULT,1))

    def test_unassessed_boundary_does_not_enter_fs_workflow(self):
        from backend.workflow import validate_request
        request=json.loads((ROOT/'models/rainfall_column_example.json').read_text())
        request['column'].update(formulation='cell_centred',surface_boundary='reviewed_infiltration')
        with self.assertRaisesRegex(ValueError,'offline hydrology'):
            validate_request(request)


@unittest.skipUnless(ready(),'Build pinned OHQ console for reviewed-boundary checks.')
class ReviewedNativeTests(unittest.TestCase):
    def test_excess_conservation_independent_integration_and_hydrostatic_limit(self):
        with tempfile.TemporaryDirectory() as folder:a=simulate(folder,SPEC,.05)
        b=reference(4,1/480/24,spec=SPEC,surface_boundary='reviewed_infiltration',failure_depth_m=.05)
        self.assertLess(a['water_balance_max_residual_m3'],1e-10)
        self.assertLess(b['water_balance_max_residual_m3'],1e-8)
        self.assertTrue(all(row['surface_storage_m3']==0 for row in a['profiles']))
        self.assertGreater(a['profiles'][-1]['surface_excess_m3'],.04)
        self.assertLess(max(abs(x['head_m']-y['head_m']) for x,y in zip(a['pressure_history'],b['pressure_history'])),1e-6)
        self.assertLess(max(abs(x['surface_excess_m3']-y['surface_excess_m3']) for x,y in zip(a['profiles'],b['profiles'])),1e-8)
        # Independent sealed hydrostatic limit with zero surface pressure: psi=d.
        for d,p in zip(a['reference_depths_m'],a['profiles'][-1]['pressure_head_m']):self.assertAlmostEqual(d,p,places=7)
        stored=sum(retention(d,SPEC)[0]*SPEC['depth_m']/SPEC['cells'] for d in a['reference_depths_m'])
        expected=SPEC['depth_m']*SPEC['initial_theta']+.05-stored
        self.assertAlmostEqual(a['profiles'][-1]['surface_excess_m3'],expected,places=9)

    def test_rain_limited_and_no_rain_do_not_create_surface_water_supply(self):
        with tempfile.TemporaryDirectory() as folder:
            for rain in (0.,1.):
                s={**SPEC,'initial_theta':.3,'duration_h':.25,'rain_duration_h':.25,'rainfall_mm_h':rain}
                a=simulate(Path(folder)/str(rain),s,.05)
                self.assertLess(a['water_balance_max_residual_m3'],1e-10)
                self.assertAlmostEqual(a['profiles'][-1]['surface_excess_m3'],0.,places=12)
                self.assertAlmostEqual(a['profiles'][-1]['cumulative_net_infiltration_m3'],rain*.25/1000,places=12)

    def test_manufactured_pressurized_column_can_exfiltrate_without_rain(self):
        # The native compressible branch begins at Se=.999. This valid,
        # near-saturated initial theta has positive head above the shallow cell
        # centre and must discharge, even when the rainfall supply is zero.
        s={**SPEC,'initial_theta':.399999,'specific_storage_per_m':.0001,'rainfall_mm_h':0.,'rain_duration_h':0.,'duration_h':.25}
        with tempfile.TemporaryDirectory() as folder:a=simulate(folder,s,.05)
        self.assertLess(a['water_balance_max_residual_m3'],1e-10)
        self.assertGreater(a['profiles'][-1]['surface_excess_m3'],0.)
        self.assertLess(a['profiles'][-1]['cumulative_net_infiltration_m3'],0.)
        self.assertTrue(all(row['surface_storage_m3']==0 for row in a['profiles']))


if __name__=='__main__':unittest.main()
