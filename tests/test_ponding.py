from pathlib import Path
import tempfile
import unittest

from hydrology.column import ready, simulate
from validation.ponding import SPEC, FAILURE_DEPTH, differences, hydrostatic_surface_depth, reference


class PondingReferenceTests(unittest.TestCase):
    def test_transition_conservation_and_exact_hydrostatic_limit(self):
        result=reference(32,.0005)
        self.assertLess(result['water_balance_max_residual_m3'],2e-8)
        self.assertLess(result['pressure_history'][0]['head_m'],0)
        self.assertEqual(result['pressure_history'][0]['surface_depth_m'],0)
        final=result['pressure_history'][-1]
        surface=hydrostatic_surface_depth()
        self.assertGreater(surface,0)
        self.assertAlmostEqual(final['surface_depth_m'],surface,places=6)
        self.assertAlmostEqual(final['head_m'],surface+FAILURE_DEPTH,places=6)
        self.assertGreater(min(result['profiles'][-1]['theta']),SPEC['theta_sat'])


@unittest.skipUnless(ready(),'Build pinned OHQ console for ponding/saturation diagnostics.')
class PondingOHQTests(unittest.TestCase):
    def test_production_transition_and_discrete_hydrostatic_limit(self):
        fine=reference(64,.00025)
        with tempfile.TemporaryDirectory() as temp:
            cases=[simulate(Path(temp)/str(n),{**SPEC,'cells':n},FAILURE_DEPTH) for n in (8,16,32)]
        errors=[differences(case,fine)['maximum_failure_pressure_difference_m'] for case in cases]
        self.assertGreater(errors[0],errors[1]);self.assertGreater(errors[1],errors[2])
        # These comparisons quantify a remaining error; they do not certify
        # transient accuracy by merely accepting a loose pressure tolerance.
        for n,case in zip((8,16,32),cases):
            self.assertLess(case['water_balance_max_residual_m3'],1e-7)
            last=case['profiles'][-1]
            self.assertGreater(min(last['theta']),SPEC['theta_sat'])
            self.assertGreater(case['pressure_history'][-1]['head_m'],0)
            # Analytic mass balance for the production top-reference grid.
            span=SPEC['theta_sat']-SPEC['theta_res']
            capacity=span*SPEC['specific_storage_per_m']/SPEC['theta_sat']
            correction=capacity*SPEC['depth_m']**2/(2*n*(1+capacity*SPEC['depth_m']))
            self.assertAlmostEqual(last['surface_storage_m3'],hydrostatic_surface_depth()+correction,places=6)


if __name__=='__main__':unittest.main()
