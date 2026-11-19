# Local API

Start with `python3 -m backend.server`. The API and front end share the same loopback origin. No CORS access is provided. Responses use JSON except the three static front-end assets. This initial service is not configured for public deployment.

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Current pressure mode and pinned engine metadata; OHQ hydrology availability is explicitly false |
| `POST /api/jobs` | Validate and queue a JSON scenario; return 202 and job status |
| `GET /api/jobs` | Latest 50 job statuses |
| `GET /api/jobs/<id>` | State, progress, and message |
| `GET /api/jobs/<id>/request` | Stored normalized scenario |
| `GET /api/jobs/<id>/provenance` | Engine pin, calculation mode, and source SHA-256 hashes |
| `GET /api/jobs/<id>/result` | Completed result; 409 until available |
| `DELETE /api/jobs/<id>` | Cancel queued or running work; terminal jobs return 409 |

Requests must use `Content-Type: application/json` and be at most 256 KiB. See `models/prescribed_pressure_example.json` for a complete request. Modes are `deterministic` and `ensemble`. Each mechanical parameter provides `value`, `min`, and `max`; deterministic mode uses `value`. The history contains strictly increasing nonnegative `time_h` and finite `head_m` values. All mechanical ranges must contain their nominal value.

States are `queued`, `running`, `completed`, `failed`, `cancelled`, and `interrupted`. Invalid requests return 400 before creating a job. Domain failures during execution produce a failed job with a message, not a partial result. Queue saturation returns 429. Cancellation is cooperative between realizations. Restarting the server preserves terminal jobs and marks unfinished work interrupted.

Each job directory contains `request.json`, `status.json`, `provenance.json`, and, if successful, `result.json`. No endpoint accepts uploaded executable commands, model paths, or arbitrary filesystem paths. Persistence is local JSON files; there is no database or multi-user permission model.
