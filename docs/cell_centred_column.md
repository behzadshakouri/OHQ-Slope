# Selectable cell-centred column formulation

The column adapter supports `column.formulation = "cell_centred"` alongside the
original `"legacy_top"` formulation. Requests without this optional field keep
the legacy equations and pressure references. Existing saved jobs are not
recomputed or relabelled. The browser exposes the choice under **Column
formulation**; both remain research models.

## Components and governing discretization

The project-owned [`components/cell_centred_column.json`](../components/cell_centred_column.json)
loads through `addtemplate`. It defines two connectors, without copying the Soil
component, editing the pinned engine, or changing Soil's upstream `head`
expression. Each connector explicitly computes the soil representative elevation
as `bottom_elevation + depth/2`.

For homogeneous vertical cells, downward flux per unit area is:

```text
H_i = bottom_elevation_i + dz_i/2 + psi_i
K_face = (K(theta_i) + K(theta_j))/2
q_ij = K_face * (H_i - H_j) / [(dz_i + dz_j)/2]
```

The soil storage, clipped van Genuchten–Mualem relationships, and compressible
excess-storage branch remain the pinned OHQ Soil laws. Arithmetic conductivity
is an explicit discretization choice for this uniform-column model, not a claim
that it is optimal for arbitrary heterogeneous layers.

At the surface, `H_surface = ponding_depth` and the unsmoothed Darcy capacity is:

```text
q_capacity = Ksat * (ponding_depth - psi_first + dz_first/2) / (dz_first/2)
dh/dt = rainfall - q_actual
```

The connector's `applylimit` setting uses OHQ's existing nonnegative-storage
active-set algorithm. When unconstrained outflow would empty the surface, the
engine solves for a flow multiplier with zero remaining surface storage. This
implements water availability instead of multiplying flux by `h/(h+0.001)`.
Reverse exchange is permitted by the head gradient and constrained by the source
block's available water. The adapter rejects a native surface storage below
-1e-10 m³; it does not clip or silently repair such a result.

The independent verification solver implements its own backward-Euler/Newton
surface balance using `min(rainfall+h_old/dt, q_capacity)`. Agreement checks both
the JSON expressions and the engine's limiting behavior, without reusing its
implementation. A sealed base and the existing unit-gradient drainage connector
are supported. There is no runoff outlet, ET, lateral flow, or layered geometry.

## Pressure mapping and reproducibility

Cell-centred models support 2–64 cells; legacy models retain the 2–32 limit.
The existing 120-second native solver allowance and 125-second child timeout
remain in force, so larger grids are not guaranteed to finish for every input.

For N equal cells of total depth L, representative depths are
`(i+0.5)*L/N`. Failure depth must be between `L/(2N)` and `L-L/(2N)`; extrapolation
above or below those references is rejected. The adapter interpolates total
head at the failure depth and removes the failure-plane elevation. The legacy
formulation retains its top-reference interval and original connectors.

The chosen formulation, representative depths, pressure convention, custom
component hash, native minimum surface storage, water balance, binary identity,
and initial-state convention are included in results. Server provenance also
snapshots the component source. Hydraulic uncertainty keeps the chosen
formulation fixed for every realization. Either Python or OHQ JSON FS can consume
the mapped pressures; all existing mechanical domain checks still apply.

The cell-centred solver requests Newton tolerance 1e-10; the legacy path retains
1e-8. This is separate from the user-selected maximum time step. Time-zero
observation placeholders are reconstructed from specified initial states in
both modes. No production solver limit or submodule pin is changed.

## Run and verify

```sh
python3 -m uncertainty.run models/cell_centred_example.json --output results/cell-centred-example.json
python3 -m validation.cell_centred --output results/cell-centred-check.json
```

The example is a synthetic 0.5 m, 32-cell sealed column with a 0.25 m failure
depth, 40 mm/h rainfall for three hours, and six-hour duration. It runs the OHQ
JSON FS component after the hydrology. The smaller 1/240-hour maximum step is
illustrative and is not an accuracy guarantee for another case.

The verification matrix covers ponded sealed flow, lighter rainfall, drier and
wetter initial states, unit-gradient drainage, and no rain. It compares 8/16/32
OHQ cells against both the same-grid independent solver and a 128-cell reference,
with separate independent 64/128-cell and time-step differences. Full-profile
differences are reported separately from pressure at the selected failure plane.
Each case writes an isolated summary and raw OHQ files; the final report records
source and engine hashes. `--case NAME` selects an individual regime.
`--cells 16 32 64 --reference-cells 256` selects finer grids; these runs can
be substantially slower. Failed runs raise an error rather than reporting
partial comparisons as a completed study.

## Measured synthetic checks

Local pinned-engine runs use maximum step 1/240 h and outputs every 0.25 h.
The first three columns below are maximum failure-plane pressure differences
from the independent 128-cell calculation, in metres. The last compares complete
32-cell profiles with an independent calculation on the **same** grid.

| Regime | OHQ 8 cells vs 128 | OHQ 16 vs 128 | OHQ 32 vs 128 | 32-cell matched-grid profile difference |
|---|---:|---:|---:|---:|
| ponded_sealed | 0.0914954 | 0.030312 | 0.0100923 | 4.37744e-08 |
| light_rain | 0.019434 | 0.00533108 | 0.00130528 | 2.70553e-09 |
| initially_drier | 0.730417 | 0.261256 | 0.122254 | 0.000213189 |
| initially_wetter | 0.0184775 | 0.00552112 | 0.00206859 | 6.414e-08 |
| drained | 0.0914065 | 0.0302962 | 0.00814954 | 3.45345e-08 |
| no_rain | 0.000257169 | 7.17699e-05 | 1.77597e-05 | 1.53398e-06 |

Errors at the failure plane decrease with grid refinement in all six cases,
but the dry initial state (theta=0.20) remains poorly resolved at 32 cells:
its 0.122 m difference is much larger than its 0.000214 m same-grid full-profile
difference. The independent 64/128-cell pressure difference is itself 0.0383 m;
that reference is not an exact transient solution. Halving OHQ's 32-cell step
changes the dry-case pressure by 0.00238 m. In the base ponded case, those
independent-grid and OHQ-time differences are 0.00347 and 0.00158 m respectively.
These comparisons separate implementation, spatial, and temporal sensitivity;
they are not rigorous error bounds or universal acceptance thresholds.

All sampled surfaces remain nonnegative. Raw native surface minima are also
checked by the adapter. Across the matrix, maximum native water-balance residual is below 2e-11 m³;
the independent matched-grid residual is below 6.3e-8 m³. Water balance and
drainage are checked independently;
the regression suite additionally covers a near-saturated initial state, JSON FS
coupling, hydraulic sampling, and HTTP submission. Generated reports and native
files remain local under ignored `results/`; the commands above regenerate them.

### Finer dry-case check

The successful 64-cell OHQ check against an independent 256-cell reference gives
maximum failure-pressure difference 0.05278 m. Its same-grid failure-pressure
and full-profile differences are 0.000618 and 0.000912 m. The independent
128/256-cell pressure difference is 0.01455 m, while halving the reference step
changes pressure by 0.00478 m. Halving OHQ's 64-cell step changes it by 0.00360 m.
The native water-balance residual is below 1.4e-13 m³. Thus finer cells help,
but neither calculation establishes a converged dry wetting front.

```sh
python3 -m validation.cell_centred --case initially_drier --cells 64 --reference-cells 256 --output results/cell-centred-dry-refinement.json
```

### Offline runtime diagnosis

The earlier 128-cell dry-case failure has now been reproduced with the native
solution logger enabled. The log explicitly reports `Simulation time exceeded
the limit of 120 seconds`; it stopped at t=0.065431264 days (about 1.57 h), before
the requested 0.25 days. The solver cost profile records about 110 seconds in
residual evaluation. Exit code 5 alone did not identify this cause.

`validation.runtime_diagnosis` provides a bounded offline diagnostic with a
separate engine allowance and a process guard five seconds longer. It enables
`solution_details.txt`, saves explicit failed/completed trial status, and uses
the same pressure mapping and conservation checks as normal runs. It allows
64/128 cells only in this diagnostic; web/API inputs remain capped at 64 cells
with their existing 120/125-second engine/process limits. No engine source or
pin is changed.

```sh
python3 -m validation.runtime_diagnosis --engine-seconds 120 --output results/runtime-128-limited.json
python3 -m validation.runtime_diagnosis --engine-seconds 600 --compare --output results/runtime-128-extended.json
python3 -m validation.runtime_diagnosis --engine-seconds 600 --half-step --compare --output results/runtime-128-half-step.json
```

The optional comparison calculates independent matched-grid and 256-cell
references plus reference grid/time sensitivity. Generated logs and reports stay
under ignored `results/`. Research progress and the study checkpoint stay in
Dropbox. A successful longer run alone would not establish spatial convergence
or justify expanding the app's grid cap.

### Completed 128-cell dry-case checks

With a 600-second offline engine allowance, the 1/240-hour maximum-step run
completed in about 300 seconds including process setup and postprocessing. The
1/480-hour run completed in about 387 seconds. Both covered the full six hours;
minimum surface storage was zero, and maximum water-balance residuals were
2.38e-10 and 3.61e-11 m³ respectively. Runtime depends on the machine and load.

At the 0.25 m failure depth, the 128-cell maximum pressure difference from the
256-cell independent reference is 0.01413 m, compared with 0.05278 m for 64 OHQ
cells against that same reference. The independent 128/256-cell difference is
0.01455 m and its 256-cell time-step difference is 0.00478 m. These are still
numerical references with unresolved error.

The 128-cell same-grid failure-pressure difference is 0.00125 m, but the full
profile difference reaches 0.02246 m at t=0.75 h and depth 0.177734375 m
(OHQ -2.17042 m, reference -2.14795 m). Halving OHQ's maximum step changes the
failure-plane pressure by 0.00407 m and the complete profiles by up to 0.02350 m.
All maxima here are over saved times, not a bound on unsampled states. This
supports improved grid agreement at the selected depth while leaving wetting-front
time sensitivity unresolved; it does not validate failure timing or the entire
pressure field.

At the smaller step, same-grid OHQ/reference disagreement falls to 0.000310 m
at the failure plane and 0.000476 m over the full profiles. Halving the independent
128-cell step also changes its profiles by 0.02351 m, closely matching OHQ's
0.02350 m change. This points to temporal resolution of the sharp front as a
remaining numerical issue, rather than establishing a discrepancy in the chosen
constitutive laws. Next checks should reduce the time step again and assess
reference spatial sensitivity at consistent steps before quantitative inference.

## Remaining limits

Implementation agreement and conservation do not establish continuum accuracy,
experimental validation, or reliable failure timing. Resolve and report grid/time
sensitivity for the intended case, then compare measured hydrologic responses.
The saturated storage law itself is shared with the reference, so its physical
validity is not independently established by this comparison. FS still omits
ponded-water mechanical surcharge and suction strength, and no experimental
parameters or joint probability distributions are inferred by selecting this
formulation.
