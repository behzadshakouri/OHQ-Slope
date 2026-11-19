import math
import unittest
from stability.infinite_slope import factor_of_safety, ModelDomainError
from uncertainty.ensemble import run, validate


def scenario(mode='deterministic', samples=1):
    values = {'cohesion_kpa': 0, 'friction_deg': 35, 'unit_weight_kn_m3': 20,
              'slope_deg': 30, 'failure_depth_m': 2}
    return {'mode': mode, 'samples': samples, 'seed': 42,
            'parameters': {name: {'value': value, 'min': value, 'max': value}
                           for name, value in values.items()},
            'pressure_history': [{'time_h': 0, 'head_m': 0}, {'time_h': 1, 'head_m': 1}]}


class StabilityTests(unittest.TestCase):
    def test_dry_cohesionless_limit(self):
        fs = factor_of_safety(0, 35, 20, 30, 2, 0)
        self.assertAlmostEqual(fs, math.tan(math.radians(35))/math.tan(math.radians(30)))

    def test_independent_force_balance(self):
        # beta=45 degrees: total normal=driving=20 kPa; pore=9.81 kPa;
        # cohesion=2 kPa, tan(phi)=1 -> resistance=12.19 kPa.
        self.assertAlmostEqual(factor_of_safety(2, 45, 20, 45, 2, 1), 12.19/20)

    def test_pressure_reduces_fs_and_suction_is_omitted(self):
        dry = factor_of_safety(3, 30, 18, 30, 2, 0)
        self.assertEqual(dry, factor_of_safety(3, 30, 18, 30, 2, -10))
        self.assertLess(factor_of_safety(3, 30, 18, 30, 2, 1), dry)

    def test_loss_of_contact_is_not_a_probability_sample(self):
        with self.assertRaises(ModelDomainError):
            factor_of_safety(2, 30, 18, 30, 1, 10)

    def test_fixed_ensemble_matches_deterministic(self):
        a = run(scenario())
        b = run(scenario('ensemble', 20))
        self.assertEqual(a['series'], b['series'])
        self.assertEqual(b['event_probability'], 1)
        self.assertEqual(b['first_sampled_crossing_h'], [1]*20)

    def test_seeded_uncertainty_is_repeatable(self):
        request=scenario('ensemble', 50)
        request['parameters']['friction_deg'].update(min=25, max=45)
        self.assertEqual(run(request), run(request))

    def test_event_probability_aggregates_each_realization(self):
        request=scenario('ensemble', 200)
        request['parameters']['friction_deg'].update(min=25, max=45)
        result=run(request)
        expected=sum(fs<1 for fs in result['minimum_fs_samples'])/200
        self.assertEqual(result['event_probability'], expected)
        self.assertGreater(expected, 0)
        self.assertLess(expected, 1)
        self.assertFalse(result['ohq_hydrology_used'])

    def test_single_realization_keeps_ensemble_semantics(self):
        result = run(scenario('ensemble', 1))
        self.assertEqual(result['distribution'], 'independent uniform mechanical inputs')

    def test_reject_bad_inputs(self):
        for replacement in (float('nan'), float('inf'), True):
            req=scenario();req['parameters']['cohesion_kpa']['value']=replacement
            with self.assertRaises(ValueError):validate(req)
        req=scenario();req['pressure_history'][1]['time_h']=0
        with self.assertRaises(ValueError):validate(req)
        req=scenario('ensemble',10000);req['pressure_history']=[{'time_h': i, 'head_m': 0} for i in range(101)]
        with self.assertRaises(ValueError):validate(req)

if __name__ == '__main__':unittest.main()
