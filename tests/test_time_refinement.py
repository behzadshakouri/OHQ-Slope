import copy
import unittest

from validation.time_refinement import compare


def report(step):
    spec={'cells':2,'depth_m':.5,'solver_step_h':step,'formulation':'cell_centred'}
    hydro={'specification':spec,'engine_binary_sha256':'binary','component_sha256':'component',
           'failure_depth_m':.25,'pressure_mapping':'centres','water_balance_max_residual_m3':0.,
           'minimum_surface_storage_m3':0.,'reference_depths_m':[.125,.375],
           'pressure_history':[{'time_h':0.,'head_m':0.,'surface_depth_m':0.},
                               {'time_h':1.,'head_m':step,'surface_depth_m':0.}],
           'profiles':[{'time_h':0.,'pressure_head_m':[0.,0.]},
                       {'time_h':1.,'pressure_head_m':[step,step]}]}
    return {'state':'completed','trial':{'state':'completed','specification':spec,'hydrology':hydro},
            'engine_dependency':{'commit':'engine'}}


class TimeRefinementTests(unittest.TestCase):
    def test_known_first_order_differences_without_implied_acceptance(self):
        result=compare([report(1/240),report(1/480),report(1/960)])
        ratio=result['halving_ratios'][0]
        self.assertAlmostEqual(ratio['failure_pressure']['difference_ratio'],2.)
        self.assertAlmostEqual(ratio['profile']['empirical_order'],1.)
        self.assertEqual(result['acceptance_status'],'not_assessed')
        self.assertIsNone(result['rows'][0]['matched_failure_pressure'])

    def test_mismatched_physics_engine_or_steps_are_rejected(self):
        for field in ('depth','binary','step','failed','mapping'):
            with self.subTest(field=field):
                reports=[report(1/240),report(1/480),report(1/960)]
                last=reports[-1];hydro=last['trial']['hydrology']
                if field=='depth':hydro['specification']['depth_m']=.6
                elif field=='binary':hydro['engine_binary_sha256']='other'
                elif field=='step':hydro['specification']['solver_step_h']=1/1000
                elif field=='failed':last['trial']['state']='failed'
                else:hydro['pressure_mapping']='tops'
                with self.assertRaises(ValueError):compare(reports)

    def test_reference_matched_by_actual_step_and_grid(self):
        reports=[report(1/240),report(1/480),report(1/960)]
        # A legacy reference can reside in another report; never identify its
        # time step from the enclosing native result's position in the list.
        ref=copy.deepcopy(reports[1]['trial']['hydrology'])
        ref.update(cells=2,step_days=1/480/24)
        ref['variant']={'head_reference':'centre','conductivity':'arithmetic','surface_boundary':'complementarity'}
        reports[0]['matched_reference_half_step']=ref
        result=compare(reports)
        self.assertIsNone(result['rows'][0]['matched_failure_pressure'])
        self.assertEqual(result['rows'][1]['matched_profile_difference_m'],0.)
        self.assertIsNone(result['rows'][2]['matched_failure_pressure'])
        ref['variant']['head_reference']='top'
        with self.assertRaisesRegex(ValueError,'different discrete equations'):compare(reports)


if __name__=='__main__':unittest.main()
