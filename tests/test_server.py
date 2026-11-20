import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from backend.server import Jobs, handler_for, write_json
from test_stability import scenario
from hydrology.column import ready


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.jobs = Jobs(self.temp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.jobs))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.jobs.close();self.temp.cleanup()

    def request(self, method, path, data=None, headers=None):
        client=http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        body=json.dumps(data) if data is not None else None
        request_headers={'Content-Type':'application/json', **(headers or {})}
        client.request(method,path,body,request_headers)
        response=client.getresponse();raw=response.read();status=response.status
        mime=response.getheader('Content-Type');client.close()
        return status, json.loads(raw) if mime=='application/json' else raw

    def wait_for(self, job_id):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            item=self.jobs.get(job_id)
            if item['state'] not in ('queued','running'):return item
            time.sleep(.01)
        self.fail('Job did not terminate')

    def test_full_run_and_download(self):
        for path in ('/','/style.css','/app.js'):
            self.assertEqual(self.request('GET',path)[0],200)
        code,health=self.request('GET','/api/health')
        self.assertEqual(code,200);self.assertEqual(health['ohq_hydrology_available'],ready())
        code,job=self.request('POST','/api/jobs',scenario('ensemble',30))
        self.assertEqual(code,202)
        self.assertEqual(self.wait_for(job['id'])['state'],'completed')
        code,result=self.request('GET',f"/api/jobs/{job['id']}/result")
        self.assertEqual(code,200);self.assertEqual(result['samples'],30)
        self.assertFalse(result['ohq_hydrology_used'])
        self.assertEqual(self.request('GET',f"/api/jobs/{job['id']}/request")[0],200)
        self.assertEqual(self.request('GET',f"/api/jobs/{job['id']}/provenance")[0],200)
        self.assertEqual(self.request('GET','/api/jobs')[1]['jobs'][0]['id'],job['id'])

    @unittest.skipUnless(ready(), 'Build OHQ before coupled HTTP check.')
    def test_ohq_job_uses_simulated_pressure(self):
        from test_hydrology import column_request
        request=column_request()
        request['column'].update(duration_h=2,rain_duration_h=1)
        code,job=self.request('POST','/api/jobs',request)
        self.assertEqual(code,202)
        status=self.wait_for(job['id'])
        self.assertEqual(status['state'],'completed',status['message'])
        _,result=self.request('GET',f"/api/jobs/{job['id']}/result")
        self.assertTrue(result['ohq_hydrology_used'])
        self.assertLess(result['hydrology']['water_balance_max_residual_m3'],1e-7)

    @unittest.skipUnless(ready(), 'Build OHQ before scheduled rainfall HTTP check.')
    def test_scheduled_rainfall_request_and_provenance(self):
        from hydrology.column import ROOT
        request=json.loads((ROOT/'models/repeated_rainfall_example.json').read_text())
        code,job=self.request('POST','/api/jobs',request)
        self.assertEqual(code,202)
        status=self.wait_for(job['id'])
        self.assertEqual(status['state'],'completed',status['message'])
        _,stored=self.request('GET',f"/api/jobs/{job['id']}/request")
        _,result=self.request('GET',f"/api/jobs/{job['id']}/result")
        _,provenance=self.request('GET',f"/api/jobs/{job['id']}/provenance")
        self.assertEqual(stored['column']['rainfall_schedule'],request['column']['rainfall_schedule'])
        self.assertEqual(stored['column']['rainfall_mm_h'],0)
        self.assertAlmostEqual(result['hydrology']['rainfall_total_m'],.04869)
        self.assertIn('hydrology/rainfall.py',provenance['source_sha256'])
        request['column']['rainfall_schedule'][1]['start_h']=0
        self.assertEqual(self.request('POST','/api/jobs',request)[0],400)

    @unittest.skipUnless(ready(), 'Build OHQ before hydraulic HTTP check.')
    def test_cell_centred_job_and_json_stability_provenance(self):
        from test_hydrology import column_request
        from validation.ponding import SPEC
        request=column_request()
        request['column']={**SPEC,'formulation':'cell_centred','duration_h':1,'rain_duration_h':1}
        request['parameters']['failure_depth_m']={'value':.25,'min':.25,'max':.25}
        request['stability_engine']='ohq_json'
        code,job=self.request('POST','/api/jobs',request)
        self.assertEqual(code,202)
        status=self.wait_for(job['id'])
        self.assertEqual(status['state'],'completed',status['message'])
        _,result=self.request('GET',f"/api/jobs/{job['id']}/result")
        _,provenance=self.request('GET',f"/api/jobs/{job['id']}/provenance")
        self.assertEqual(result['hydrology']['formulation'],'cell_centred')
        self.assertTrue(result['stability_diagnostic']['python_reference_checked'])
        self.assertEqual(result['hydrology']['component_sha256'],provenance['source_sha256']['components/cell_centred_column.json'])

    @unittest.skipUnless(ready(), 'Build OHQ before hydraulic HTTP check.')
    def test_hydraulic_job_runs_distinct_realizations(self):
        from test_coupled import request
        scenario=request();scenario['samples']=2
        scenario['column'].update(duration_h=2,rain_duration_h=1)
        code,job=self.request('POST','/api/jobs',scenario)
        self.assertEqual(code,202)
        status=self.wait_for(job['id'])
        self.assertEqual(status['state'],'completed',status['message'])
        _,result=self.request('GET',f"/api/jobs/{job['id']}/result")
        self.assertTrue(result['hydraulic_uncertainty_sampled'])
        self.assertEqual(len(result['realizations']),2)
        self.assertIn('pressure_p95_m',result['series'][-1])
        self.assertNotEqual(result['realizations'][0]['hydraulic'],result['realizations'][1]['hydraulic'])

    def test_input_errors_and_origin(self):
        self.assertEqual(self.request('POST','/api/jobs',{})[0],400)
        self.assertEqual(self.request('POST','/api/jobs',scenario(),{'Origin':'https://other.example'})[0],403)
        self.assertEqual(self.request('POST','/api/jobs',scenario(),{'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('GET','/config/engine.json')[0],404)
        self.assertEqual(self.request('GET','/api/jobs/../request')[0],404)
        self.assertEqual(self.request('GET','/api/health',headers={'Host':'attacker.example'})[0],403)
        self.assertEqual(self.jobs.list(),[])

    def test_domain_failure_is_explicit(self):
        req=scenario();req['pressure_history'][1]['head_m']=10
        code,job=self.request('POST','/api/jobs',req)
        self.assertEqual(code,202)
        item=self.wait_for(job['id'])
        self.assertEqual(item['state'],'failed');self.assertIn('normal stress',item['message'])
        self.assertEqual(self.request('GET',f"/api/jobs/{job['id']}/result")[0],409)


class RecoveryTests(unittest.TestCase):
    def test_restart_marks_incomplete_jobs_interrupted(self):
        with tempfile.TemporaryDirectory() as temp:
            job_id='a'*32;folder=Path(temp)/job_id;folder.mkdir()
            write_json(folder/'status.json',{'id':job_id,'state':'running','created_utc':'2026-01-01'})
            jobs=Jobs(temp)
            try:self.assertEqual(jobs.get(job_id)['state'],'interrupted')
            finally:jobs.close()

    def test_shutdown_interrupts_queued_jobs(self):
        with tempfile.TemporaryDirectory() as temp:
            jobs=Jobs(temp)
            gate=threading.Event();jobs.pool.submit(gate.wait)
            job=jobs.submit(scenario())
            release=threading.Timer(.02,gate.set);release.start()
            jobs.close();release.join()
            self.assertEqual(jobs.get(job['id'])['state'],'interrupted')

    def test_queued_cancel_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            jobs=Jobs(temp)
            # Hold the only worker so the submitted simulation remains queued.
            gate=threading.Event();jobs.pool.submit(gate.wait)
            try:
                job=jobs.submit(scenario())
                self.assertEqual(jobs.cancel(job['id'])['state'],'cancelled')
            finally:
                gate.set();jobs.close()
            self.assertEqual(jobs.get(job['id'])['state'],'cancelled')

if __name__=='__main__':unittest.main()
