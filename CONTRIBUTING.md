# Contributing

Use GitHub issues for reproducible bugs, scientific questions, and scoped feature
proposals. Include the scenario JSON, commit, engine/build identity, and relevant
error or water-balance diagnostics. Keep credentials, private datasets, generated
binaries, large outputs, and paper materials outside commits.

For every new model, boundary condition or engine workflow, inspect the pinned
OHQ templates, examples and tools first. Reuse a stock component when its
equations, units and boundary behavior match the case. If a capability is
missing and the OHQ interpreter can express it, add a focused JSON component
under `components/` and benchmark it through the native console. If it needs
an algorithm the interpreter cannot express, document the missing primitive
and extend OHQ upstream. See [OHQ reuse across the project](docs/development.md#ohq-reuse-across-the-project).

New calculations should state their equations, units, pressure/depth conventions,
valid domain, and verification evidence. When changing flow physics, distinguish
conservation, agreement with the same discrete equations, spatial/time convergence,
and experimental validation. JSON/Python FS parity does not establish hydrologic
accuracy. Add a meaningful regression check for a changed numerical behavior.

Run the existing checks before submitting:

```sh
python3 -m unittest discover -s tests -v
node --check frontend/app.js
python3 scripts/check_dependency.py
```

OHQ-dependent tests require the pinned console build described in the README.
Without that build, those tests are explicitly skipped. Changes to the engine
belong in a separately reviewed OHQ branch; update the submodule pin deliberately.
Keep unrelated local engine changes out of this project.

The project uses AGPL-3.0-or-later for its newly authored code. Preserve upstream
copyright and license notices when adapting code. See [NOTICE.md](NOTICE.md).
