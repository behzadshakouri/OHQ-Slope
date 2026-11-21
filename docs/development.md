# Development notes

Keep hydrology, stability, and ensemble orchestration behind small interfaces. The initial app runs the external FS reference calculation on prescribed pressure histories. An initial coupling now runs the pinned headless OHQ console for a synthetic rainfall column. Pressure mapping follows its top-reference convention; transient spatial accuracy still requires independent benchmarking. Do not duplicate the complete Soil template as the initial extension strategy.

The separate JSON diagnostic is now implemented in `components/infinite_slope.json`. The optional `ohq_json` workflow uses its FS values and checks every realization against the Python reference. It runs after external pressure mapping, without cross-block reads or feedback into hydrology. Ponding/saturation diagnostics identify a remaining transient pressure discrepancy; do not treat mechanical parity as hydrologic validation. See [JSON implementation](json_stability.md) and [flow verification](verification.md).

The external stability calculation will consume time, pressure at specified failure surfaces, geometry, and mechanical parameters. Define units, pressure sign, angle convention, and failure geometry explicitly before implementation. Do not equate block thickness with failure depth or assume representative block pressure is bottom pressure.

Verify water balance, initial conditions, independent ensemble initialization, numerical run status, and sampling resolution. Record input and template hashes, seed, distributions, engine commit, build settings, and solver settings for each ensemble. Treat numerical failures separately from physical instability.

Only use generated kernels after comparison with the interpreter. Regenerate them when models or templates change. Check that parameter updates affect intended quantities and initial states.

Engine fixes belong in an OHQ branch with appropriate validation. Update this project's submodule pin deliberately. Changes from the original working checkout are not included in this dependency baseline.

External reference datasets should be described by a local configuration or manifest with checksums and provenance. Do not copy paper assets into this repository. A reproducible small synthetic benchmark belongs here.

The seismic extension will initially use a pseudostatic coefficient and rainfall-conditioned pressures. Dynamic deformation, liquefaction, and shaking-generated pore pressure require separately scoped mechanics.

## OHQ reuse across the project

Use OpenHydroQual as the modeling engine for all supported production
workflows. Inspect the pinned submodule before implementing a new equation,
boundary, process, diagnostic or calibration tool.

1. **Stock OHQ first.** Compose existing blocks, links, sources, observations
   and native orchestration or calibration tools. Check definitions and
   units in the pinned templates, and exercise them against a small solvable case.
2. **Custom OHQ JSON for missing behavior.** Add the smallest block, link or
   diagnostic that expresses the missing equations. Preserve reusable stock
   components, test the new template in the native interpreter, and compare its
   equation limits or output against an independent reference.
3. **Upstream engine support when needed.** If the interpreter or solver
   cannot express the required behavior, identify the missing primitive and
   test an engine extension in the upstream OHQ repository before moving the
   submodule pin.
4. **Python around the engine.** Use Python for model assembly, data conversion,
   pressure mapping, job management, verification, result analysis and
   reporting. Keep standalone numerical implementations as independent
   benchmarks. Existing Python execution paths can be migrated after their
   native counterparts pass equivalent regression checks.

| Area | Reuse first | Capability to verify or extend |
|---|---|---|
| Hydrology and seepage | Native `Soil`, surface and groundwater blocks, horizontal and vertical soil links, rainfall sources, fixed-head links and `soil_free_outflow`. | Verify assembled grids, interface conductance, seepage-face elevation and infiltration/runoff partitioning. Reuse the existing cell-centred and reviewed-surface JSON where the stock equations differ from the benchmark. |
| Stability and seismic loading | Use the existing verified OHQ-JSON infinite-slope diagnostic. Add suitable pressure, strength or prescribed pseudostatic force expressions in JSON when the interpreter supports them. | Verify each force balance and its valid domain. Establish whether geometry, search and dynamic mechanics require upstream primitives. |
| Stress and deformation | Check the pinned engine for constitutive state, stress equilibrium and staged loading support. | No native geotechnical stress–strain solver has been verified here. Define the capability and validate the smallest engine extension if JSON balances and expressions are insufficient. |
| Water quality and thermal processes | Start with native mass-transfer templates, reaction cases and the upstream Thermal Discharge Pond example. | Verify the specific porous-media transport and boundary equations before extending to heat, air or contaminants in a slope. |
| Calibration and uncertainty | Evaluate the pinned OHQ-LM, OHQ-GA and OHQ-MCMC tools when their objective and inference assumptions fit the task. | Verify tool builds, parameter binding and reproducibility. The current forward Monte Carlo orchestrator is a separate workflow and requires equivalent sampling and output checks before replacement. |

### Retrospective audit

- `d652add` pinned OHQ at project initialization. `7a593f2` introduced the native
  rainfall-column workflow, and subsequent column physics continued to run in
  OHQ. Python reference integrators were added to verify those runs.
- `8bd9ddf` introduced Python factor-of-safety analysis and forward sampling.
  `4b3a9d1` added the verified OHQ JSON stability diagnostic. The browser now
  prefers that diagnostic when OHQ is available. Explicit older scenarios and
  API/CLI requests with no engine selection retain their original semantics.
- The Python-only rectangular 2D solver at `eb82fbc` is an analytical
  verification reference. The native two-column grid reuses OHQ soil and
  horizontal links and the existing cell-centred vertical and surface templates.
- Hydraulic table fitting and forward sampling remain external. Calibration
  migration is conditional on verifying the relevant OHQ tool against the
  actual objective, parameters and output requirements.

## Interface and service status

The local front end and job back end are implemented. Both web jobs and the CLI call the same stability/ensemble code. The server uses a single worker and isolated job folders; long-term scheduling, live sensors, forecast cycling, and data assimilation remain deferred. This is a local research app, not an authenticated public service.

## Modeling coverage roadmap

The near-term goal is to reproduce the seepage, stability and deformation
analyses used in the archived slope case. Each increment needs an analytical
or independent numerical benchmark before it is used to interpret the case.

| Analysis | Current OHQ-Slope scope | Modeling work |
|---|---|---|
| Seepage | One-dimensional saturated/unsaturated columns and a [standalone 2D saturated reference](seepage_2d.md) with lateral flow, imposed infiltration, and an atmospheric outlet | Assemble a native 2D unsaturated model from existing soil components, then add sloping boundaries, material zones, and infiltration/runoff partitioning. Establish 3D requirements after 2D checks. |
| Slope stability | Infinite slope with supplied or column-derived pore pressure | Define suction strength and external water loading, then add finite slope geometry, slice equilibrium and slip-surface search with benchmark cases. |
| Stress and deformation | Archive inventory and a pressure interface to the existing stability model | Define displacement, stress, material laws and staged construction. Verify a standalone mechanical reference before coupling pore pressure and deformation. |
| Seismic response | Rainfall-conditioned pore pressure histories | First verify pseudostatic stability. Dynamic response, cyclic strength and shaking-generated pore pressure require their own models and benchmarks. |
| Heat, air and contaminant transport | Outside the current slope workflow | Scope individual transport equations, material laws, boundary conditions and coupled benchmarks after the slope workflow is established. |

The archive inventory reveals saved analyses and outputs even when a solver
for those analyses is unavailable. When adding field readers, preserve analysis,
step, mesh and variable identities so that a comparison uses the correct geometry
and units. Use the [wetting-front benchmark](column_sensitivity.md#synthetic-wetting-front-benchmark)
as the starting regression case for seepage development.
