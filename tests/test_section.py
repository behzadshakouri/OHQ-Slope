import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from backend.server import Jobs
from hydrology.column import ROOT, initial_pressure, ready
from hydrology.section import prepare, simulate_section


def example():
    return json.loads((ROOT/'models/seepage_2d_example.json').read_text())


class SectionInputTests(unittest.TestCase):
    def test_zone_stack_and_pressure_initialization(self):
        case = example()
        second = copy.deepcopy(case['materials']['soil'])
        second.pop('initial_theta')
        second['initial_pressure_head_m'] = -.7
        case['materials']['lower_soil'] = second
        case['columns'][0]['materials'][-1] = 'lower_soil'
        _, zones, rainfall = prepare(case)
        self.assertAlmostEqual(initial_pressure(zones[0][-1]), -.7, places=8)
        self.assertNotEqual(zones[0][0]['initial_theta'], zones[0][-1]['initial_theta'])
        self.assertEqual(rainfall[-1], [])

    def test_rejects_probe_outside_cell_centres(self):
        case = example()
        case['probes']['toe']['elevation_m'] = .3
        with self.assertRaisesRegex(ValueError, 'toe elevation_m'):
            prepare(case)


@unittest.skipUnless(ready(), 'Build the pinned OHQ console for native scenario tests.')
class NativeSectionTests(unittest.TestCase):
    def test_job_reproduces_stepped_benchmark(self):
        with TemporaryDirectory() as folder:
            jobs = Jobs(Path(folder))
            try:
                job = jobs.submit({'analysis':'seepage_2d','section':example()})
            finally:
                jobs.pool.shutdown(wait=True)
            self.assertEqual(jobs.get(job['id'])['state'], 'completed')
            path = Path(folder)/job['id']
            result = json.loads((path/'result.json').read_text())
            provenance = json.loads((path/'provenance.json').read_text())
            self.assertEqual(provenance['calculation'], 'native_seepage_2d_v1')
        outlet = result['hydrology']['outlet_history'][-1]
        self.assertAlmostEqual(outlet['cumulative_runoff_m3'], .000530248741680831, places=10)
        self.assertAlmostEqual(outlet['cumulative_discharge_m3'], .0002475801101911419, places=10)
        self.assertLess(result['hydrology']['water_balance_max_residual_m3'], 1e-7)

    def test_distinct_zones_conserve_initial_water(self):
        case = example()
        case['materials']['lower_soil'] = dict(case['materials']['soil'], initial_theta=.3, ksat_m_day=.25)
        case['columns'][0]['materials'][-1] = 'lower_soil'
        case['duration_h'] = case['output_interval_h'] = .0125
        for column in case['columns']:
            column['rainfall'] = []
        with TemporaryDirectory() as folder:
            result = simulate_section(folder, case)
        grid = result['hydrology']
        self.assertAlmostEqual(grid['histories'][0][0]['theta'][-1], .3)
        self.assertLess(grid['water_balance_max_residual_m3'], 1e-7)


if __name__ == '__main__':
    unittest.main()
