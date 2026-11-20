# OHQ-Slope

[![Checks](https://github.com/behzadshakouri/OHQ-Slope/actions/workflows/checks.yml/badge.svg)](https://github.com/behzadshakouri/OHQ-Slope/actions/workflows/checks.yml)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](#run-locally)
[![License: AGPL v3 or later](https://img.shields.io/badge/License-AGPL--3.0--or--later-blue)](LICENSE)
[![Status: research prototype](https://img.shields.io/badge/Status-research%20prototype-orange)](#current-capability)

Rainfall-driven slope stability and uncertainty quantification with
[OpenHydroQual](https://openhydroqual.com/), verified infinite-slope mechanics,
and a local scenario app.

[Run locally](#run-locally) · [Governing calculation](docs/calculation.md) · [JSON component](docs/json_stability.md) · [Verification](docs/verification.md) · [Contributing](CONTRIBUTING.md)

## About

OHQ-Slope connects a pinned OpenHydroQual rainfall-column model to a uniform
infinite-slope factor-of-safety calculation. A browser workspace, local job
service, and command-line runner share the same workflow. Seeded ensembles
propagate mechanical uncertainty and, optionally, hydraulic uncertainty through
separate OHQ realizations.

The stability calculation is available as a Python reference and as a custom OHQ
JSON component, checked against the reference for every realization. Conservation,
analytical limits, independent flow comparisons, and numerical refinement checks
are reported separately from experimental validation. Live digital-twin operation
remains a future stage.

## Current capability

- Configure a uniform infinite slope with either an OHQ rainfall column or a prescribed pressure history.
- Calculate FS with the Python reference or a custom OHQ JSON diagnostic, with per-realization agreement checks.
- Select sealed or unit-gradient drainage, inspect pressure response, and check water conservation.
- Choose legacy top-reference or cell-centred JSON flow connectors, with explicit pressure mapping and formulation provenance.
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

For the new cell-centred hydrologic formulation, choose it under **Column
formulation** or run:

```sh
python3 -m uncertainty.run models/cell_centred_example.json --output results/cell-centred-example.json
```

Existing requests keep the legacy
model. See [cell-centred equations and verification](docs/cell_centred_column.md).

For repeated rainfall, choose **Repeated or variable rainfall** in the interface or run `python3 -m uncertainty.run models/repeated_rainfall_example.json --output results/repeated-rainfall.json`. See [schedule inputs and verification](docs/rainfall_schedules.md).

The browser, API, and command-line runner use the same workflow, stability, and uncertainty modules. See [the calculation specification](docs/calculation.md) and [API contract](docs/api.md).

## Verify

```sh
python3 -m unittest discover -s tests -v
node --check frontend/app.js
python3 scripts/check_dependency.py
```

Node is optional for the JavaScript syntax check. HTTP integration tests need permission to open local loopback sockets. Tests cover analytical force balances, pressure effects, uncertainty reproducibility, job handling, column water balance and drainage, pressure mapping, selected refinement checks, and coupled HTTP runs. OHQ integration tests are explicitly skipped when the console is not built. Browser visual inspection remains a separate check.

## OHQ dependency

### OpenHydroQual resources

| Resource | Link |
|---|---|
| Project website | [openhydroqual.com](https://openhydroqual.com/) |
| Documentation and tutorials | [OpenHydroQual knowledge base](https://openhydroqual.com/knowledge-base/) |
| Example models | [Examples portal](https://examples.openhydroqual.com/) · [source repository](https://github.com/ArashMassoudieh/OpenHydroQual-Examples) |
| Source code and releases | [ArashMassoudieh/OpenHydroQual](https://github.com/ArashMassoudieh/OpenHydroQual) |

### Pinned source and build

```sh
git submodule update --init --recursive
python3 scripts/check_dependency.py
```

Build the console out of tree:

```sh
python3 scripts/build_ohq.py --qmake /path/to/Qt/gcc_64/bin/qmake
```

Qt6, a C++17 compiler, make, Armadillo, LAPACK/BLAS, GSL, and SuperLU are required; see upstream build instructions for platform details. The helper records binary provenance under ignored `build/ohq-console/`. No executable or generated kernel is committed. The pinned engine has been built locally and checked with synthetic column cases, not field validated. See [column conventions and verification limits](docs/column.md), including the time-zero observation workaround and unresolved transient spatial sensitivity. [Independent flow checks](docs/verification.md) cover analytical diffusion, nonlinear unsaturated infiltration, and ponding/saturation. The legacy ponding case has a transient pressure difference of about 0.044 m at 32 cells. The selectable cell-centred version improves that comparison, while its drier wetting-front case still needs finer-grid investigation.

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
| `OpenHydroQual/` | Pinned engine submodule |
| `results/` | Ignored generated outputs |

## Next development stages

1. Establish case-specific spatial/time accuracy of the implemented [cell-centred formulation](docs/cell_centred_column.md) across regimes before quantitative experimental inference.
2. Validate pressure representation and mechanical surface-loading assumptions before interpreting failure timing.
3. Establish evidence-based joint parameter distributions and benchmark comparable experimental cases.
4. Extend the implemented JSON diagnostic where justified; verify interpreter/kernel parity before enabling generated kernels.
5. Add rainfall-conditioned pseudostatic seismic assessment.

The front end and back end are part of the current application. Live sensors, scheduled forecasts, state assimilation, and other digital-twin functions are deferred. See [development notes](docs/development.md).

## Dependencies and licensing

OHQ-Slope's newly authored code and documentation are distributed under
[AGPL-3.0-or-later](LICENSE). OpenHydroQual and jsoncpp retain their upstream
licenses and notices; see [NOTICE.md](NOTICE.md).

## Citation and project metadata

If you use this software, cite [CITATION.cff](CITATION.cff) and record the exact
Git commit used for your calculations. Cite OpenHydroQual separately for the
simulation engine, following its upstream publication and documentation.

The repository About description and topic tags are tracked in
[.github/repository.json](.github/repository.json). These GitHub settings require
a separate authenticated update; see [repository metadata](docs/repository_metadata.md).
The Checks workflow runs after pushing and explicitly skips native OHQ checks
when its console has not been built. A passing CI badge is not field validation.
