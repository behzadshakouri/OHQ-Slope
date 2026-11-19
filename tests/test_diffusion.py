from pathlib import Path
import tempfile
import unittest
from hydrology.column import ready
from validation.diffusion import benchmark


@unittest.skipUnless(ready(),'Build pinned OHQ console for the analytical diffusion check.')
class DiffusionTests(unittest.TestCase):
    def test_refinement_toward_analytical_decay(self):
        with tempfile.TemporaryDirectory() as temp:
            coarse=benchmark(Path(temp)/'8',8)
            fine=benchmark(Path(temp)/'16',16)
        self.assertLess(fine['maximum_head_error_m'],coarse['maximum_head_error_m'])
        self.assertLess(fine['relative_to_initial_amplitude'],.002)

if __name__=='__main__':unittest.main()
