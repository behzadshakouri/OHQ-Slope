from pathlib import Path
import tempfile
import unittest

from hydrology.column import ready, simulate
from validation.ponding import SPEC, FAILURE_DEPTH, differences, hydrostatic_surface_depth, reference
from validation.ponding_ablation import PRODUCTION, variant


class ControlledReferenceTests(unittest.TestCase):
    def test_variant_validation_and_top_grid_equilibrium(self):
        with self.assertRaises(ValueError):reference(8,head_reference='unsupported')
        result=reference(16,.0005,**variant(PRODUCTION))
        self.assertLess(result['water_balance_max_residual_m3'],2e-8)
        span=SPEC['theta_sat']-SPEC['theta_res']
        capacity=span*SPEC['specific_storage_per_m']/SPEC['theta_sat']
        correction=capacity*SPEC['depth_m']**2/(2*16*(1+capacity*SPEC['depth_m']))
        self.assertAlmostEqual(result['pressure_history'][-1]['surface_depth_m'],hydrostatic_surface_depth()+correction,places=6)


@unittest.skipUnless(ready(),'Build pinned OHQ console for matched-law verification.')
class MatchedLawTests(unittest.TestCase):
    def test_ohq_matches_independent_solver_for_same_discrete_laws(self):
        ref=reference(32,.000125,**variant(PRODUCTION))
        with tempfile.TemporaryDirectory() as temp:
            case=simulate(Path(temp),{**SPEC,'cells':32,'solver_step_h':SPEC['solver_step_h']/4},FAILURE_DEPTH)
        # This checks time integration of the existing laws, not the physical
        # choice of top-reference nodes, maximum K, or a smoothed boundary.
        self.assertLess(differences(case,ref)['maximum_failure_pressure_difference_m'],.003)


if __name__=='__main__':unittest.main()
