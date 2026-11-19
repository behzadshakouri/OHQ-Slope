from pathlib import Path
import tempfile
import unittest

from hydrology.column import ready
from validation.infiltration import SPEC, compare, ohq_case, reference


class ReferenceTests(unittest.TestCase):
    def test_independent_reference_resolution_and_balance(self):
        coarse, medium, fine = reference(32), reference(64), reference(128)
        spatial = compare(medium,fine)['maximum_profile_difference_m']
        self.assertLess(spatial,compare(coarse,medium)['maximum_profile_difference_m']/2)
        self.assertLess(spatial,1e-4)
        temporal = compare(medium,reference(64,.075))['maximum_profile_difference_m']
        self.assertLess(temporal,1e-6)
        self.assertLess(fine['maximum_water_balance_residual_m'],1e-10)
        # A sealed base accumulates water, while rainfall wets the top.
        final = fine['profiles'][-1]['pressure_m']
        self.assertGreater(final[0],SPEC['initial_pressure_m'])
        self.assertGreater(final[-1],SPEC['initial_pressure_m'])
        self.assertTrue(all(p < 0 for p in final))


@unittest.skipUnless(ready(),'Build pinned OHQ console for the nonlinear infiltration comparison.')
class InfiltrationTests(unittest.TestCase):
    def test_ohq_refines_toward_independent_nonlinear_reference(self):
        fine = reference(128)
        with tempfile.TemporaryDirectory() as temp:
            cases = [ohq_case(Path(temp)/str(n),n) for n in (8,16,32)]
        errors = [compare(case,fine)['maximum_profile_difference_m'] for case in cases]
        self.assertGreater(errors[0],errors[1])
        self.assertGreater(errors[1],errors[2])
        # Case-specific tolerance at three saved times, not a general error bound.
        self.assertLess(errors[-1],.004)
        for case in cases:
            self.assertLess(case['maximum_water_balance_residual_m'],1e-10)


if __name__ == '__main__': unittest.main()
