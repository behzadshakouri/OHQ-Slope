import math
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from backend.workflow import execute, validate_request
from hydrology.column import ready
from stability.infinite_slope import ModelDomainError
from stability.ohq_diagnostic import evaluate
from test_coupled import fake_column, request as coupled_request
from test_stability import scenario


def state(**overrides):
    return {**dict(cohesion_kpa=5,friction_deg=30,unit_weight_kn_m3=18,
                   slope_deg=30,failure_depth_m=1,pressure_head_m=0),**overrides}


class DiagnosticGuards(unittest.TestCase):
    def test_domain_and_cancellation_reject_before_launch(self):
        with tempfile.TemporaryDirectory() as temp,patch('stability.ohq_diagnostic.run_engine') as engine:
            with self.assertRaises(ModelDomainError):evaluate(Path(temp),[state(pressure_head_m=10)])
            with self.assertRaises(InterruptedError):evaluate(Path(temp),[state()],lambda:True)
            engine.assert_not_called()

    def test_parity_failure_rejects_result(self):
        with tempfile.TemporaryDirectory() as temp,patch('stability.ohq_diagnostic.run_engine',return_value={
            'factor_of_safety_0':[(0,0),(24e-6,123)],'contact_valid_0':[(0,0),(24e-6,1)]}):
            with self.assertRaisesRegex(ValueError,'differs from Python'):
                evaluate(Path(temp),[state()])

    def test_engine_and_budget_validation(self):
        r=scenario('ensemble',101);r['stability_engine']='ohq_json'
        with self.assertRaisesRegex(ValueError,'100 realizations'):validate_request(r)
        r=scenario();r['stability_engine']='unknown'
        with self.assertRaisesRegex(ValueError,'stability engine'):validate_request(r)


@unittest.skipUnless(ready(),'Build pinned OHQ console to check JSON stability.')
class DiagnosticIntegrationTests(unittest.TestCase):
    def test_independent_limits_and_angle_range(self):
        rows=[state(cohesion_kpa=0,friction_deg=30,slope_deg=45)]
        # Exercise the angle representation near both API bounds as well as
        # pressure clipping and a broad set of intermediate angles.
        for beta in (.1,10,30,60,89):
            for phi in (.01,20,45,89):
                rows.extend([state(slope_deg=beta,friction_deg=phi,pressure_head_m=-2),
                             state(slope_deg=beta,friction_deg=phi,pressure_head_m=0)])
        rng=random.Random(18)
        for _ in range(20):
            beta=rng.uniform(.1,89);weight=rng.uniform(1,40);depth=rng.uniform(.01,100)
            head=.8*weight*depth*math.cos(math.radians(beta))**2/9.81
            rows.append(state(slope_deg=beta,friction_deg=rng.uniform(.01,89),
                              unit_weight_kn_m3=weight,failure_depth_m=depth,pressure_head_m=head))
        with tempfile.TemporaryDirectory() as temp:result=evaluate(Path(temp),rows)
        self.assertAlmostEqual(result['factor_of_safety'][0],math.tan(math.pi/6)/math.tan(math.pi/4),places=12)
        self.assertTrue(result['python_reference_checked'])

    def test_seeded_ensemble_uses_json_values_with_reference_parity(self):
        r=scenario('ensemble',4)
        with tempfile.TemporaryDirectory() as temp:
            baseline=execute(r,Path(temp)/'python')
            result=execute({**r,'stability_engine':'ohq_json'},Path(temp)/'json')
        self.assertEqual(result['stability_engine'],'ohq_json')
        self.assertEqual(result['stability_diagnostic']['realizations_checked'],4)
        self.assertEqual(result['event_probability'],baseline['event_probability'])
        for a,b in zip(result['series'],baseline['series']):self.assertAlmostEqual(a['median'],b['median'],places=10)

    def test_hydraulic_ensemble_checks_each_paired_state(self):
        r=coupled_request();r.update(samples=2,stability_engine='ohq_json')
        with tempfile.TemporaryDirectory() as temp,patch('uncertainty.coupled.simulate',side_effect=fake_column):
            result=execute(r,Path(temp))
        self.assertEqual(result['stability_diagnostic']['realizations_checked'],2)
        self.assertTrue(result['hydraulic_uncertainty_sampled'])


if __name__=='__main__':unittest.main()
