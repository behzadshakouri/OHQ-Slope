import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.workflow import execute, validate_request
from hydrology.column import DEFAULT, initial_pressure, map_pressure, ready, simulate, validate_column, set_initial_observations

ROOT=Path(__file__).resolve().parents[1]


def column_request():
    return json.loads((ROOT/'models/rainfall_column_example.json').read_text())


class MappingTests(unittest.TestCase):
    def test_hydrostatic_total_head_mapping(self):
        # Constant H=0.2 m at elevations 0,-0.5,-1 gives psi .2,.7,1.2.
        self.assertAlmostEqual(map_pressure([.2,.7,1.2],[0,.5,1],.75),.95)

    def test_uniform_pressure_mapping(self):
        self.assertAlmostEqual(map_pressure([-.8,-.8,-.8],[0,.5,1],.75),-.8)
        with self.assertRaises(ValueError):map_pressure([0,1],[0,1],1.1)

    def test_initial_retention_pressure(self):
        psi=initial_pressure(DEFAULT)
        m=1-1/DEFAULT['n']
        se=(1+(DEFAULT['alpha_per_m']*abs(psi))**DEFAULT['n'])**(-m)
        theta=DEFAULT['theta_res']+(DEFAULT['theta_sat']-DEFAULT['theta_res'])*se
        self.assertAlmostEqual(theta,DEFAULT['initial_theta'])

    def test_column_request_constraints(self):
        req=column_request();req['mode']='ensemble'
        req['parameters']['failure_depth_m']['max']=1.2
        with self.assertRaises(ValueError):validate_request(req)
        with self.assertRaises(ValueError):validate_column({**DEFAULT,'n':1},1)
        with self.assertRaises(ValueError):validate_column(DEFAULT,2)
        req=column_request();req['pressure_source']='unexpected'
        with self.assertRaises(ValueError):validate_request(req)

    def test_initial_output_mismatch_is_rejected(self):
        observations={'surface_storage':[(0,0),(1,0)],'drainage_storage':[(0,0),(1,0)]}
        for i in range(DEFAULT['cells']):
            observations.update({f'storage_{i}':[(0,.01),(1,.01)],
                                 f'theta_{i}':[(0,.3),(1,.3)],
                                 f'pressure_{i}':[(0,-1),(1,-1)]})
        with self.assertRaisesRegex(ValueError,'initial observation'):
            set_initial_observations(observations,DEFAULT)

    def test_missing_binary_is_explicit(self):
        with patch('hydrology.column.ready',return_value=False):
            with tempfile.TemporaryDirectory() as temp:
                with self.assertRaisesRegex(ValueError,'not built'):
                    simulate(Path(temp),DEFAULT,1)


@unittest.skipUnless(ready(),'Build pinned OHQ console to run hydrologic integration tests.')
class OHQTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        cls.wet=simulate(cls.root/'wet',DEFAULT,1)
        cls.dry=simulate(cls.root/'dry',{**DEFAULT,'rainfall_mm_h':0},1)
        cls.drained=simulate(cls.root/'drained',{**DEFAULT,'base':'unit_gradient'},1)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_mass_conservation_for_both_boundaries(self):
        for result in (self.wet,self.dry,self.drained):
            self.assertLess(result['water_balance_max_residual_m3'],1e-7)
        self.assertGreater(self.drained['profiles'][-1]['drainage_m3'],0)
        self.assertEqual(self.wet['profiles'][-1]['drainage_m3'],0)

    def test_rainfall_reaches_failure_plane(self):
        self.assertAlmostEqual(self.wet['pressure_history'][0]['head_m'],initial_pressure(DEFAULT))
        self.assertGreater(self.wet['pressure_history'][-1]['head_m'],self.dry['pressure_history'][-1]['head_m'])
        self.assertLess(self.drained['pressure_history'][-1]['head_m'],self.wet['pressure_history'][-1]['head_m'])
        # A sealed ponded column approaches hydrostatic equilibrium.
        last=self.wet['profiles'][-1]
        for depth,pressure in zip(self.wet['reference_depths_m'],last['pressure_head_m']):
            self.assertAlmostEqual(pressure-depth,last['surface_storage_m3'],places=4)

    def test_temporal_refinement(self):
        finer=simulate(self.root/'half-step',{**DEFAULT,'solver_step_h':DEFAULT['solver_step_h']/2},1)
        maximum=max(abs(a['head_m']-b['head_m']) for a,b in zip(self.wet['pressure_history'],finer['pressure_history']))
        self.assertLess(maximum,.03) # Demonstration-specific tolerance, not a universal error bound.

    def test_spatial_refinement_of_equilibrium(self):
        finer=simulate(self.root/'fine-grid',{**DEFAULT,'cells':32},1)
        self.assertLess(abs(self.wet['pressure_history'][-1]['head_m']-finer['pressure_history'][-1]['head_m']),.005)
        # This checks late hydrostatic equilibrium only. Transient resolution
        # remains material and is quantified separately in docs/column.md.

    def test_coupled_fs_matches_standalone(self):
        from stability.infinite_slope import factor_of_safety
        request=column_request()
        request['column']={**DEFAULT,'duration_h':2,'rain_duration_h':1}
        result=execute(request,self.root/'coupled')
        params={key:value['value'] for key,value in request['parameters'].items()}
        for row in result['series']:
            self.assertAlmostEqual(row['median'],factor_of_safety(**params,pressure_head_m=row['pressure_head_m']))
        self.assertTrue(result['ohq_hydrology_used'])
        self.assertEqual(result['pressure_source'],'ohq_column')

if __name__=='__main__':unittest.main()
