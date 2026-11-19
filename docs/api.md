# Local API

Start with `python3 -m backend.server`. The API and front end share the same loopback origin. No CORS access is provided. Responses use JSON except the three static front-end assets. This initial service is not configured for public deployment.

| Endpoint | Behavior |
|---|---|
| `GET /api/health` | Supported pressure modes, pinned engine metadata, and local OHQ console availability |
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

## Rainfall column requests

Set `pressure_source` to `ohq_column` and provide `column` as in `models/rainfall_column_example.json`. No pressure-history field is required. The adapter generates that history from OHQ, checks mass conservation, then calculates FS. Set `pressure_source` to `prescribed_history` (the default for older requests) to use a supplied history. Column mode requires fixed failure depth, including equal min/value/max in ensemble mode; other mechanical inputs can vary. Hydraulic parameters remain fixed unless per-realization hydraulic sampling is enabled as described below.

Completed single-column results (deterministic or mechanical-only ensembles) include `hydrology`: the specification, cell-reference depths, pressure/moisture profiles, surface and drainage storage, water-balance residual, binary checksum, build provenance, and initial-state convention. Submitted provenance records the requested coupling; the result's `ohq_hydrology_used` records the completed calculation mode. Raw OHQ outputs and logs remain in the local job's `hydrology/` folder and are not exposed as arbitrary downloadable paths.

## Per-realization hydraulic sampling

For an ensemble in column mode, add a nonempty `hydraulic_uncertainty` object. Each key is one of `ksat_m_day`, `alpha_per_m`, `n`, or `initial_theta` and contains `min`, `max`, and `distribution` (`uniform` or `log_uniform`). Example:

```json
{"hydraulic_uncertainty":{"ksat_m_day":{"min":0.35,"max":0.65,"distribution":"log_uniform"}}}
```

Hydraulic jobs are limited to 100 realizations. Ranges must contain nominal values and remain physically admissible. A distinct OHQ solve is performed for each sample. Results set `hydraulic_uncertainty_sampled=true`, include a `realizations` ledger, and add `pressure_p05_m` and `pressure_p95_m` to each series row; `pressure_head_m` is then the pointwise median. No single realization's profile is labelled as the ensemble profile. A failed trial fails the job without an estimated probability.
