from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hydrology.column import ready
from validation.native_seepage_2d import benchmark, outlet_benchmark, runoff_benchmark


@unittest.skipUnless(ready(), 'Build the pinned console for native grid tests.')
class NativeSeepage2DTests(unittest.TestCase):
    def test_native_uniform_and_localized_rainfall(self):
        with TemporaryDirectory() as folder:
            result = benchmark(Path(folder))
        self.assertTrue(result['passed'], result['criteria'])

    def test_native_outlet_discharge_and_suction_control(self):
        with TemporaryDirectory() as folder:
            result = outlet_benchmark(Path(folder))
        self.assertTrue(result['passed'], result['criteria'])

    def test_stock_catchment_routing_partitions_rainfall(self):
        with TemporaryDirectory() as folder:
            result = runoff_benchmark(Path(folder))
        self.assertTrue(result['passed'], result['criteria'])


if __name__ == '__main__':
    unittest.main()
