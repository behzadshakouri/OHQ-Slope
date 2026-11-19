# OHQ rainfall column adapter

## Scope

The app can now run a synthetic vertical soil column through the pinned OpenHydroQual console and feed its simulated pressure into the existing uniform infinite-slope calculation. The prescribed-pressure mode remains available. Neither mode is a field-validated slope-failure predictor.

The column has 1 m² horizontal area, uniform material properties, a ponding surface, and equal-thickness soil blocks. Rain starts at time zero at constant intensity for a specified duration, followed by a dry period. The base is sealed or has unit-gradient drainage. There is no evaporation, runoff outlet, lateral flow, or slope-parallel hydrology. This is a vertical infiltration demonstration, not a finite-slope cross-section.

The demonstration defaults to 2 m depth, 16 blocks, initial water content 0.30, Ksat 0.5 m/day, alpha 1.5/m, n 1.6, residual water content 0.05, saturated water content 0.40, specific storage 0.01/m, and pore connectivity L=0.5. Rain is 40 mm/h for six hours, with a 24-hour simulation. The failure depth is 1 m. These are synthetic values, not experimental case inputs.

## Build and execute

Build once using Qt6 qmake and the native dependencies described by upstream OHQ:

```sh
python3 scripts/build_ohq.py --qmake /path/to/Qt/gcc_64/bin/qmake
python3 -m uncertainty.run models/rainfall_column_example.json --output results/column.json
python3 -m backend.server
```

The helper builds out of tree under ignored `build/ohq-console/`, records Qt version, build commands, dependency identity, and a binary checksum in `build.json`, and leaves the engine checkout untouched. The adapter checks the binary checksum and source dependency before a run. A fresh clone must build the console before selecting column mode. In this development environment the build used `/home/arash/Qt/6.9.0/gcc_64/bin/qmake`.

The back end generates a model and forcing files under each job's `hydrology/` directory. It runs the console without a shell, captures its log, enforces an elapsed-time limit, and supports cancellation. Requests cannot choose executable paths or submit arbitrary OHQ scripts.

## Rainfall and basal drainage

OHQ precipitation CSV records contain start day, end day, and total interval depth in metres. The adapter converts mm/h and hours to those units; it does not write an intensity into the interval-depth field. A one-square-metre catchment receives precipitation with runoff coefficient one and no loss term. Its surface-to-soil link uses the existing OHQ template. With no runoff outlet, excess water remains ponded.

A small custom JSON component provides optional basal drainage Q = A K(theta), representing unit downward hydraulic gradient. A separate balance block accumulates drained volume. This collector is an accounting ledger, not a hydraulic storage controlling boundary head. The sealed option omits the basal link.

## Mapping pressures to the failure plane

In this pinned template, soil total head is `depth + bottom_elevation + pressure_head`: its elevation reference is the top of the soil block. For block i, with ground at elevation zero, the adapter uses reference depth `i * cell_thickness`. It interpolates total head between adjacent reference locations, then subtracts the failure-plane elevation to obtain pressure head. Extrapolation below the deepest available reference is prohibited.

This mapping follows the existing engine convention. It does not establish that a coarse block represents a spatially resolved continuum pressure field. Tests cover uniform-pressure and hydrostatic-total-head profiles independently of an OHQ run.

OHQ's observation containers export zero placeholders at time zero in the inspected version. The adapter replaces those initial observation entries with storage and moisture specified by the model inputs and pressure calculated from the exact clipped retention/excess-pressure formulas in the pinned template. All later pressure and moisture entries come from OHQ. This substitution is explicit in exported metadata and assumptions. No engine source patch is included.

The adapter uses the pinned engine's `OHQ_RAWOBS` export to preserve full time and value precision before output resampling; ordinary observed CSV rounds time too coarsely for tight water-balance verification. The raw export is a version-specific dependency and must be rechecked when updating OHQ.

## Conservation and verification

At every native output time, including the reconstructed initial state, check:

```text
surface_storage + sum(soil_storage) + accumulated_basal_drainage
  = initial_soil_water + cumulative_applied_rainfall
```

A residual over 1e-4 m³ (0.1 mm over the one-square-metre surface) rejects the job. The default sealed-column check closed to approximately 3e-16 m³. Tests also cover no rain, drainage, pressure mapping, the late hydrostatic limit, smaller solver steps, and agreement between coupled FS and the standalone force balance. This verifies bookkeeping and selected numerical behavior, not complete Richards-equation accuracy or slope failure timing.

A development refinement study with the same synthetic forcing and a 1 m failure depth gave:

| Comparison | Maximum transient pressure-head difference | Final pressure-head difference |
|---|---:|---:|
| 8 versus 16 blocks | 0.4983 m | 0.001075 m |
| 16 versus 32 blocks | 0.1302 m | 0.0005375 m |

Final pressure heads were approximately 1.02467, 1.02359, and 1.02306 m for 8, 16, and 32 blocks. Late hydrostatic states agree much better than transient wetting arrival. Spatial convergence of the transient solution has not been demonstrated; the default was increased from 8 to 16 blocks and the interface labels this as a prototype. Do not interpret threshold-crossing time as resolution-independent. Further refinement and comparison with an independent column solution are required before using this setup for quantitative inference.

## Stability and uncertainty limits

The failure depth is held fixed in column mode. Mechanical Monte Carlo realizations reuse one hydrologic trajectory and can vary cohesion, friction angle, total unit weight, and slope angle. With hydraulic sampling disabled, one hydrologic trajectory is reused for the mechanical ensemble. With sampling enabled, Ksat, alpha, n, and initial moisture can have independent uniform or log-uniform ranges, and each realization gets a separate OHQ solve. Failure depth and other geometry remain fixed. See [hydraulic uncertainty](hydraulic_uncertainty.md).

FS uses fixed total unit weight per realization, omits suction strength, and currently omits the mechanical surcharge of ponded surface water. It does not represent layered overburden, erosion, or changes in failure geometry. Very high pressure can exceed the frictional-contact model's normal stress; that produces an explicit failed job rather than a silently discarded realization. OHQ water content above its nominal saturated value represents the template's excess-storage/compressibility branch and should not automatically be interpreted as measured pore-volume saturation.

## Next verification work

Compare an independent Richards-equation benchmark, refine spatial resolution and output spacing, examine the representative-head convention and boundary discretization, then move to the reference experimental case. Add appropriate mechanical treatment of surface loading and an explicit unsaturated strength model if those effects are within the study scope. The reference experimental paper and report remain outside this software repository.

See [independent flow verification](verification.md) for the analytical small-amplitude diffusion check and the unresolved rainfall-grid investigation. Passing the smooth benchmark does not establish nonlinear wetting-front accuracy.
