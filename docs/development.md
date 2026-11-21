# Development notes

Keep hydrology, stability, and ensemble orchestration behind small interfaces. The initial app runs the external FS reference calculation on prescribed pressure histories. An initial coupling now runs the pinned headless OHQ console for a synthetic rainfall column. Pressure mapping follows its top-reference convention; transient spatial accuracy still requires independent benchmarking. Do not duplicate the complete Soil template as the initial extension strategy.

The separate JSON diagnostic is now implemented in `components/infinite_slope.json`. The optional `ohq_json` workflow uses its FS values and checks every realization against the Python reference. It runs after external pressure mapping, without cross-block reads or feedback into hydrology. Ponding/saturation diagnostics identify a remaining transient pressure discrepancy; do not treat mechanical parity as hydrologic validation. See [JSON implementation](json_stability.md) and [flow verification](verification.md).

The external stability calculation will consume time, pressure at specified failure surfaces, geometry, and mechanical parameters. Define units, pressure sign, angle convention, and failure geometry explicitly before implementation. Do not equate block thickness with failure depth or assume representative block pressure is bottom pressure.

Verify water balance, initial conditions, independent ensemble initialization, numerical run status, and sampling resolution. Record input and template hashes, seed, distributions, engine commit, build settings, and solver settings for each ensemble. Treat numerical failures separately from physical instability.

Only use generated kernels after comparison with the interpreter. Regenerate them when models or templates change. Check that parameter updates affect intended quantities and initial states.

Engine fixes belong in an OHQ branch with appropriate validation. Update this project's submodule pin deliberately. Changes from the original working checkout are not included in this dependency baseline.

External reference datasets should be described by a local configuration or manifest with checksums and provenance. Do not copy paper assets into this repository. A reproducible small synthetic benchmark belongs here.

The seismic extension will initially use a pseudostatic coefficient and rainfall-conditioned pressures. Dynamic deformation, liquefaction, and shaking-generated pore pressure require separately scoped mechanics.

## Interface and service status

The local front end and job back end are implemented. Both web jobs and the CLI call the same stability/ensemble code. The server uses a single worker and isolated job folders; long-term scheduling, live sensors, forecast cycling, and data assimilation remain deferred. This is a local research app, not an authenticated public service.

## Modeling coverage roadmap

The near-term goal is to reproduce the seepage, stability and deformation
analyses used in the archived slope case. Each increment needs an analytical
or independent numerical benchmark before it is used to interpret the case.

| Analysis | Current OHQ-Slope scope | Modeling work |
|---|---|---|
| Seepage | One-dimensional saturated/unsaturated columns and a [standalone 2D saturated reference](seepage_2d.md) with lateral flow, imposed infiltration, and an atmospheric outlet | Extend 2D flow to Richards-equation unsaturated storage and conductivity, then add sloping boundaries, material zones, and infiltration/runoff partitioning. Establish 3D requirements after 2D checks. |
| Slope stability | Infinite slope with supplied or column-derived pore pressure | Define suction strength and external water loading, then add finite slope geometry, slice equilibrium and slip-surface search with benchmark cases. |
| Stress and deformation | Archive inventory and a pressure interface to the existing stability model | Define displacement, stress, material laws and staged construction. Verify a standalone mechanical reference before coupling pore pressure and deformation. |
| Seismic response | Rainfall-conditioned pore pressure histories | First verify pseudostatic stability. Dynamic response, cyclic strength and shaking-generated pore pressure require their own models and benchmarks. |
| Heat, air and contaminant transport | Outside the current slope workflow | Scope individual transport equations, material laws, boundary conditions and coupled benchmarks after the slope workflow is established. |

The archive inventory reveals saved analyses and outputs even when a solver
for those analyses is unavailable. When adding field readers, preserve analysis,
step, mesh and variable identities so that a comparison uses the correct geometry
and units. Use the [wetting-front benchmark](column_sensitivity.md#synthetic-wetting-front-benchmark)
as the starting regression case for seepage development.
