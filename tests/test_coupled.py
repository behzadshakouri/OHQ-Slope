import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend.workflow import execute, validate_request
from hydrology.column import DEFAULT, ready
from stability.infinite_slope import factor_of_safety
from test_hydrology import column_request
from uncertainty.coupled import validate_ranges


def request():
    r=column_request();r.update(mode='ensemble',samples=4)
    r['hydraulic_uncertainty']={'ksat_m_day':{'min':.3,'max':.7,'distribution':'log_uniform'}}
    return r


def fake_column(folder,spec,depth,cancelled):
    return {'pressure_history':[{'time_h':0,'head_m':0},{'time_h':1,'head_m':spec['ksat_m_day']}],
            'specification':spec,'profiles':[], 'water_balance_max_residual_m3':0,
            'rainfall_total_m':.24,'reference_depths_m':[0,1], 'failure_depth_m':depth}


class CoupledTests(unittest.TestCase):
    def test_one_solve_per_realization_and_fs_pressure_consistency(self):
        with tempfile.TemporaryDirectory() as temp,patch('uncertainty.coupled.simulate',side_effect=fake_column) as simulation:
            result=execute(request(),Path(temp))
            self.assertEqual(simulation.call_count,4)
            self.assertEqual(len({str(call.args[0]) for call in simulation.call_args_list}),4)
            self.assertTrue(result['hydraulic_uncertainty_sampled'])
            self.assertGreater(result['series'][-1]['pressure_p95_m'],result['series'][-1]['pressure_p05_m'])
            for row in result['realizations']:
                expected=factor_of_safety(**row['mechanical'],pressure_head_m=row['hydraulic']['ksat_m_day'])
                self.assertAlmostEqual(row['minimum_fs'],expected)
            self.assertEqual(result['event_probability'],sum(row['minimum_fs']<1 for row in result['realizations'])/4)

    def test_seeded_joint_sampling_is_reproducible(self):
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b,patch('uncertainty.coupled.simulate',side_effect=fake_column):
            self.assertEqual(execute(request(),Path(a)),execute(request(),Path(b)))

    def test_invalid_ranges_and_limits(self):
        for ranges in ({'unknown':{'min':1,'max':2,'distribution':'uniform'}},
                       {'n':{'min':1,'max':1.8,'distribution':'uniform'}},
                       {'initial_theta':{'min':.3,'max':.5,'distribution':'uniform'}},
                       {'ksat_m_day':{'min':0,'max':1,'distribution':'log_uniform'}}):
            with self.assertRaises(ValueError):validate_ranges(ranges,DEFAULT,1)
        r=request();r['samples']=101
        with self.assertRaisesRegex(ValueError,'100 OHQ'):validate_request(r)
        r=request();r['mode']='deterministic'
        with self.assertRaisesRegex(ValueError,'ensemble mode'):validate_request(r)
        r=request();r['hydraulic_uncertainty']=[]
        with self.assertRaises(ValueError):validate_request(r)

    def test_failed_trial_has_no_probability(self):
        count=0
        def failure(*args):
            nonlocal count
            count+=1
            if count==2:raise ValueError('Synthetic solver failure')
            return fake_column(*args)
        with tempfile.TemporaryDirectory() as temp,patch('uncertainty.coupled.simulate',side_effect=failure):
            with self.assertRaisesRegex(ValueError,'No ensemble probability'):
                execute(request(),Path(temp))
            failed=json.loads((Path(temp)/'realizations/0001/status.json').read_text())
            self.assertEqual(failed['state'],'failed')
            self.assertFalse((Path(temp)/'result.json').exists())

    def test_cancellation_reaches_ohq_adapter(self):
        with tempfile.TemporaryDirectory() as temp,patch('uncertainty.coupled.simulate',side_effect=InterruptedError):
            with self.assertRaises(InterruptedError):execute(request(),Path(temp))
            self.assertEqual(json.loads((Path(temp)/'realizations/0000/status.json').read_text())['state'],'cancelled')

if __name__=='__main__':unittest.main()
