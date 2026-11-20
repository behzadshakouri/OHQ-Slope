import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from hydrology.column import run_engine
from test_stability import scenario

ROOT=Path(__file__).resolve().parents[1]


class ProcessTests(unittest.TestCase):
    def test_offline_wall_time_budget_is_bounded(self):
        for limit in (0,-1,906,float('inf'),True):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                run_engine(Path('/unused'),Path('/unused/model.ohq'),wall_time_limit_s=limit)

    def test_custom_wall_time_limit_terminates_child(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);binary=folder/'console';binary.write_bytes(b'fake executable')
            (folder/'build.json').write_text(json.dumps({'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}))
            process=Mock();process.poll.side_effect=[None,0]
            with patch('hydrology.column.BINARY',binary),patch('hydrology.column.ready',return_value=True),patch('hydrology.column.subprocess.run'),patch('hydrology.column.subprocess.Popen',return_value=process),patch('hydrology.column.time.monotonic',side_effect=[0,2]):
                with self.assertRaisesRegex(ValueError,'time limit'):
                    run_engine(folder,folder/'model.ohq',wall_time_limit_s=1)
            process.terminate.assert_called_once();process.wait.assert_called_once()

    def test_keyboard_interrupt_terminates_engine_child(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);binary=folder/'console';binary.write_bytes(b'fake executable')
            (folder/'build.json').write_text(json.dumps({'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}))
            process=Mock();process.poll.return_value=None
            def interrupt():raise KeyboardInterrupt
            with patch('hydrology.column.BINARY',binary),patch('hydrology.column.ready',return_value=True),patch('hydrology.column.subprocess.run'),patch('hydrology.column.subprocess.Popen',return_value=process):
                with self.assertRaises(KeyboardInterrupt):run_engine(folder,folder/'model.ohq',interrupt)
            process.terminate.assert_called_once();process.wait.assert_called_once()

    def test_cli_failure_replaces_old_result_with_explicit_status(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);request=scenario();request['pressure_history'][1]['head_m']=10
            source=folder/'request.json';source.write_text(json.dumps(request))
            output=folder/'output.json';output.write_text(json.dumps({'state':'completed','result':{'event_probability':0}}))
            completed=subprocess.run([sys.executable,'-m','uncertainty.run',str(source),'--output',str(output)],cwd=ROOT,capture_output=True)
            self.assertEqual(completed.returncode,1)
            data=json.loads(output.read_text())
            self.assertEqual(data['state'],'failed');self.assertNotIn('result',data)

if __name__=='__main__':unittest.main()
