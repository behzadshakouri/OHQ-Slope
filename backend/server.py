"""Local-only HTTP app with isolated job folders and a single simulation worker."""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
from urllib.parse import urlsplit
import uuid

from backend.workflow import execute, validate_request
from hydrology.column import ready

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / 'frontend'
ID = re.compile(r'^[0-9a-f]{32}$')


def write_json(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


class Jobs:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='slope')
        self.items = {}
        for path in self.folder.glob('*/status.json'):
            if not ID.fullmatch(path.parent.name):
                continue
            try:
                item = json.loads(path.read_text())
                if item.get('state') in ('queued', 'running'):
                    item.update(state='interrupted', message='Server stopped before completion; submit a new run.')
                    write_json(path, item)
                self.items[path.parent.name] = item
            except (ValueError, OSError):
                continue

    def update(self, job_id, **fields):
        with self.lock:
            self.items[job_id].update(fields)
            write_json(self.folder / job_id / 'status.json', self.items[job_id])

    def get(self, job_id):
        with self.lock:
            if job_id not in self.items:
                raise KeyError(job_id)
            return dict(self.items[job_id])

    def list(self):
        with self.lock:
            return [dict(x) for x in sorted(self.items.values(), key=lambda x: x['created_utc'], reverse=True)[:50]]

    def submit(self, request):
        request = validate_request(request)
        with self.lock:
            if sum(x['state'] in ('queued', 'running') for x in self.items.values()) >= 8:
                raise OverflowError('Eight jobs are already active; wait or cancel one.')
            job_id = uuid.uuid4().hex
            folder = self.folder / job_id
            folder.mkdir()
            write_json(folder / 'request.json', request)
            # Snapshot the requested coupling and relevant source identities.
            write_json(folder / 'provenance.json', {
                'engine': json.loads((ROOT / 'config/engine.json').read_text()),
                'calculation': 'infinite_slope_reference_v1',
                'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                    for name in ('stability/infinite_slope.py', 'stability/ohq_diagnostic.py', 'components/infinite_slope.json', 'uncertainty/ensemble.py', 'backend/server.py', 'backend/workflow.py', 'hydrology/column.py', 'uncertainty/coupled.py', 'components/column_boundaries.json', 'components/cell_centred_column.json', 'OpenHydroQual/resources/unsaturated_soil.json', 'OpenHydroQual/resources/main_components.json')},
                'stability_engine':request['stability_engine'],
                'pressure_source': request['pressure_source'], 'ohq_hydrology_requested': request['pressure_source']=='ohq_column',
            })
            self.items[job_id] = {'id': job_id, 'state': 'queued', 'progress': 0,
                'mode': request['mode'], 'samples': request['samples'],
                'created_utc': datetime.now(timezone.utc).isoformat(), 'message': 'Waiting for worker.'}
            self.update(job_id)
            self.pool.submit(self.execute, job_id, request)
            return self.get(job_id)

    def execute(self, job_id, request):
        try:
            with self.lock:
                if self.items[job_id]['state'] in ('cancelled','interrupted'):
                    return
                self.update(job_id, state='running', message='Calculating factor of safety.')
            def cancelled():
                return self.get(job_id)['state'] in ('cancelled','interrupted')
            result = execute(request, self.folder / job_id,
                             lambda value: self.update(job_id, progress=value),
                             lambda text: self.update(job_id, message=text), cancelled)
            with self.lock:
                if cancelled():
                    return
                write_json(self.folder / job_id / 'result.json', result)
                self.update(job_id, state='completed', progress=1, message='Results ready.')
        except InterruptedError:
            pass
        except Exception as error:
            with self.lock:
                if self.items[job_id]['state'] not in ('cancelled','interrupted'):
                    self.update(job_id, state='failed', message=str(error))

    def cancel(self, job_id):
        with self.lock:
            item = self.get(job_id)
            if item['state'] not in ('queued', 'running'):
                raise ValueError('Only queued or running jobs can be cancelled.')
            self.update(job_id, state='cancelled', message='Cancelled by user.')
            return self.get(job_id)

    def close(self):
        with self.lock:
            for job_id,item in self.items.items():
                if item['state'] in ('queued','running'):
                    self.update(job_id,state='interrupted',message='Server stopped; submit a new run to restart.')
        self.pool.shutdown(wait=True,cancel_futures=True)


def handler_for(jobs):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            # Request paths only, never input payloads.
            super().log_message(format, *args)

        def send(self, code, data, mime='application/json'):
            body = json.dumps(data, allow_nan=False).encode() if mime == 'application/json' else data
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self):
            port = self.server.server_port
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            host = self.headers.get('Host', '')
            origin = self.headers.get('Origin')
            if host not in hosts or (origin and origin != f'http://{host}'):
                self.send(403, {'error': 'This local app accepts same-origin localhost requests only.'})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                      '/style.css': ('style.css', 'text/css; charset=utf-8')}
            if path in assets:
                name, mime = assets[path]
                return self.send(200, (FRONTEND / name).read_bytes(), mime)
            if path == '/api/health':
                return self.send(200, {'status': 'ok', 'pressure_modes': ['prescribed_history', 'ohq_column'],
                    'ohq_hydrology_available': ready(),
                    'engine': json.loads((ROOT / 'config/engine.json').read_text())})
            if path == '/api/jobs':
                return self.send(200, {'jobs': jobs.list()})
            parts = path.strip('/').split('/')
            if len(parts) in (3, 4) and parts[:2] == ['api', 'jobs'] and ID.fullmatch(parts[2]):
                try:
                    item = jobs.get(parts[2])
                    if len(parts) == 3:
                        return self.send(200, item)
                    if parts[3] in ('request', 'result', 'provenance'):
                        if parts[3] == 'result' and item['state'] != 'completed':
                            return self.send(409, {'error': 'Results are not available.'})
                        data = json.loads((jobs.folder / parts[2] / f'{parts[3]}.json').read_text())
                        return self.send(200, data)
                except KeyError:
                    pass
            self.send(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.allowed():
                return
            if self.path != '/api/jobs':
                return self.send(404, {'error': 'Not found.'})
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                return self.send(415, {'error': 'Use application/json.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 262144:
                    return self.send(413, {'error': 'Request must be between 1 and 262144 bytes.'})
                request = json.loads(self.rfile.read(length))
                self.send(202, jobs.submit(request))
            except (ValueError, TypeError) as error:
                self.send(400, {'error': str(error)})
            except OverflowError as error:
                self.send(429, {'error': str(error)})

        def do_DELETE(self):
            if not self.allowed():
                return
            parts = self.path.strip('/').split('/')
            if len(parts) != 3 or parts[:2] != ['api', 'jobs'] or not ID.fullmatch(parts[2]):
                return self.send(404, {'error': 'Not found.'})
            try:
                self.send(200, jobs.cancel(parts[2]))
            except KeyError:
                self.send(404, {'error': 'Not found.'})
            except ValueError as error:
                self.send(409, {'error': str(error)})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--jobs-dir', type=Path, default=ROOT / 'results/jobs')
    args = parser.parse_args()
    jobs = Jobs(args.jobs_dir)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(jobs))
    print(f'OHQ-Slope running at http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.close()

if __name__ == '__main__':
    main()
