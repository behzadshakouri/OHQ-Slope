import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from validation.ponding import SPEC
from validation.runtime_diagnosis import trial


class RuntimeDiagnosisTests(unittest.TestCase):
    def test_offline_small_step_is_preserved_without_relaxing_app_guard(self):
        from hydrology.column import validate_column
        spec={**SPEC,'cells':128,'formulation':'cell_centred','solver_step_h':1/960}
        with self.assertRaises(ValueError):validate_column({**spec,'cells':64},.25)
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            with patch('validation.runtime_diagnosis.run_engine',side_effect=ValueError('test stop')):
                result=trial(folder,spec,1)
            self.assertEqual(result['state'],'failed')
            script=(folder/'column.ohq').read_text()
            self.assertIn(f'quantity=initial_time_step,value={1/960/24}\n',script)
            with self.assertRaises(ValueError):trial(folder,{**spec,'solver_step_h':1/3840},1)

    def test_failure_preserves_explicit_engine_reason_without_hydrology(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            # Stale logs must not determine the new run's diagnosis.
            (folder/'solution_details.txt').write_text('Maximum number of matrix inversions exceeded')
            def fail(*args,**kwargs):
                (folder/'solution_details.txt').write_text('Simulation time exceeded the limit of 1 seconds')
                raise ValueError('OHQ failed (exit 5)')
            spec={**SPEC,'cells':128,'formulation':'cell_centred','initial_theta':.2}
            with patch('validation.runtime_diagnosis.run_engine',side_effect=fail):
                result=trial(folder,spec,1)
            self.assertEqual(result['state'],'failed')
            self.assertEqual(result['stopping_reason'],'engine_wall_time_limit')
            self.assertNotIn('hydrology',result)
            self.assertEqual(json.loads((folder/'summary.json').read_text()),result)
            script=(folder/'column.ohq').read_text()
            self.assertIn('quantity=maximum_time_allowed,value=1\n',script)
            self.assertIn('quantity=write_solution_details,value=Yes',script)


if __name__=='__main__':unittest.main()
