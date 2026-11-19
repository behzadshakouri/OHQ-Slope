# OHQ-Slope

A local slope-stability workspace with a browser front end, a job-service back end, and independently usable scientific calculations. A pinned OpenHydroQual console supplies an optional vertical rainfall-column simulation.

## Current capability

- Configure a uniform infinite slope with either an OHQ rainfall column or a prescribed pressure history.
- Calculate FS with the Python reference or a custom OHQ JSON diagnostic, with per-realization agreement checks.
- Select sealed or unit-gradient drainage, inspect pressure response, and check water conservation.
- Run deterministic FS or seeded Monte Carlo calculations with independent uniform mechanical inputs.
- Optionally sample conductivity, retention parameters, and initial moisture using independent uniform or log-uniform ranges, with one OHQ solve per realization.
- Inspect FS time series, 5–95% ensemble bands, sampled-time instability frequency, and recent jobs.
- Download the request, result, and calculation provenance as JSON.
- Track asynchronous progress, cancel jobs, and retain results across server restarts.

**Column mode is a prototype.** It simulates vertical rainfall infiltration with surface ponding; transient grid sensitivity remains material. Prescribed-pressure mode is available without building OHQ. Mechanical-only ensembles reuse one pressure history; hydraulic ensembles run OHQ separately for each sample. Column-mode geometry and failure depth are fixed. No field validation, finite-slope geometry, seismic load, deformation, or live digital twin is implemented. Inputs and uncertainty ranges are synthetic. No paper materials are included.

## Run locally

Python 3.10 or newer is sufficient; the current app uses only its standard library. No front-end build or package installation is needed.

```sh
git clone --recurse-submodules https://github.com/behzadshakouri/OHQ-Slope.git
cd OHQ-Slope
python3 -m backend.server
```

Open **http://127.0.0.1:8765**. Build OHQ as described below to enable the rainfall-column option; otherwise select prescribed pressure. Stop with Ctrl+C. To choose another port:

```sh
python3 -m backend.server --port 8766
```

The server intentionally binds to loopback and accepts same-origin requests only. It is a local research tool; public hosting and authentication have not been implemented. Jobs are stored in ignored `results/jobs/` folders; pass `--jobs-dir /path/to/jobs` to select another location. A restart marks incomplete jobs as interrupted rather than silently resuming them.

## Run without the interface

```sh
python3 -m uncertainty.run models/prescribed_pressure_example.json --output results/example.json
```

After building OHQ, run the coupled example with `python3 -m uncertainty.run models/rainfall_column_example.json --output results/column.json`.

For a small hydraulic ensemble, use `python3 -m uncertainty.run models/hydraulic_ensemble_example.json --output results/hydraulic-ensemble.json`. In the interface choose Monte Carlo and enable “Sample hydraulic properties too”. Up to 100 OHQ solves are allowed per job; start with a small count. See [sampling details](docs/hydraulic_uncertainty.md).

To use the OHQ JSON stability component, choose it under **Stability calculation**, or run `python3 -m uncertainty.run models/json_stability_example.json --output results/json-stability.json`. It requires the built console, supports up to 100 realizations and 10,000 sample-time evaluations, and checks every FS against Python before reporting results. See [JSON component details](docs/json_stability.md).

The browser, API, and command-line runner use the same workflow, stability, and uncertainty modules. See [the calculation specification](docs/calculation.md) and [API contract](docs/api.md).

## Verify

```sh
python3 -m unittest discover -s tests -v
node --check frontend/app.js
python3 scripts/check_dependency.py
```

Node is optional for the JavaScript syntax check. HTTP integration tests need permission to open local loopback sockets. Tests cover analytical force balances, pressure effects, uncertainty reproducibility, job handling, column water balance and drainage, pressure mapping, selected refinement checks, and coupled HTTP runs. OHQ integration tests are explicitly skipped when the console is not built. Browser visual inspection remains a separate check.

## OHQ dependency

```sh
git submodule update --init --recursive
python3 scripts/check_dependency.py
```

Build the console out of tree:

```sh
python3 scripts/build_ohq.py --qmake /path/to/Qt/gcc_64/bin/qmake
```

Qt6, a C++17 compiler, make, Armadillo, LAPACK/BLAS, GSL, and SuperLU are required; see upstream build instructions for platform details. The helper records binary provenance under ignored `build/ohq-console/`. No executable or generated kernel is committed. The pinned engine has been built locally and checked with synthetic column cases, not field validated. See [column conventions and verification limits](docs/column.md), including the time-zero observation workaround and unresolved transient spatial sensitivity. [Independent flow checks](docs/verification.md) cover analytical diffusion, nonlinear unsaturated infiltration, and ponding/saturation. The latter finds a remaining transient pressure difference of about 0.044 m at 32 cells in its synthetic case, despite close final water levels.

## Structure

| Directory | Purpose |
|---|---|
| `frontend/` | Buildless browser interface and SVG charts |
| `backend/` | Local HTTP API, persistent job records, single simulation worker |
| `stability/` | Infinite-slope Python reference and OHQ JSON diagnostic adapter |
| `hydrology/` | OHQ column generation, process adapter, pressure mapping, and conservation checks |
| `uncertainty/` | Seeded ensemble calculation and CLI |
| `models/` | Synthetic runnable input specifications |
| `tests/` | Scientific and HTTP integration checks |
| `validation/` | Analytical diffusion, nonlinear infiltration, ponding/saturation, and rainfall refinement diagnostics |
| `components/` | Column boundaries and read-only infinite-slope JSON diagnostic |
| `config/` | Engine provenance |
| `external/OpenHydroQual/` | Pinned engine submodule |
| `results/` | Ignored generated outputs |

## Next development stages

1. Resolve the transient pressure gap identified by the independent ponding/saturation comparison and establish spatial convergence.
2. Validate pressure representation and mechanical surface-loading assumptions before interpreting failure timing.
3. Establish evidence-based joint parameter distributions and benchmark comparable experimental cases.
4. Extend the implemented JSON diagnostic where justified; verify interpreter/kernel parity before enabling generated kernels.
5. Add rainfall-conditioned pseudostatic seismic assessment.

The front end and back end are part of the current application. Live sensors, scheduled forecasts, state assimilation, and other digital-twin functions are deferred. See [development notes](docs/development.md).

## Dependencies and licensing

OpenHydroQual retains its upstream license in `external/OpenHydroQual/LICENSE`. No separate license for newly authored project code is selected yet.
