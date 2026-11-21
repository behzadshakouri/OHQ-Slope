# Offline hydrology-only column sensitivity

`validation.column_sensitivity` runs a grid/time matrix from an external JSON
study. Case geometry, extracted archive data, fitted parameters and research
interpretation remain outside the software repository. No FS is evaluated.

An external study supplies `formulation_role: "hydrology_only"`, a complete
`column` specification, and a `points` list.
Each point needs a unique `id` and `vertical_depth_m`. Additional coordinate
and provenance fields are preserved, allowing the same hydrology to be sampled
at several observation depths without equating those depths to slip surfaces.

```sh
python3 -m validation.column_sensitivity /absolute/path/study.json --cells 16 32 64 --step-divisions 240 480 --engine-seconds 600 --output results/column-study.json
```

For cell-centred studies the offline runner accepts up to 256 cells, a
3.75-second maximum step (`--step-divisions 960`), and output intervals as
short as one minute (`output_interval_h: 0.016666666666666666`). Keep high
resolution runs short enough to fit the explicit 1–900 second engine allowance.
The process guard allows five additional seconds. The native study retains the
physical-input limits and the 50,000 nominal-step and 500 output-time bounds.
The web and API keep their current resolution and runtime limits.

For a focused first-pulse check, make a copy of the external study, set
`duration_h` to the intended cutoff, and retain only rainfall intervals inside
that window, clipping the final interval to the cutoff if needed. Run cases
with different combinations of grid and maximum step separately if they do
not form a complete matrix.

```sh
python3 -m validation.column_sensitivity /absolute/path/first-pulse.json --cells 128 256 --step-divisions 480 --engine-seconds 900 --output results/first-pulse-grid.json
python3 -m validation.column_sensitivity /absolute/path/first-pulse.json --cells 128 --step-divisions 480 960 --engine-seconds 900 --output results/first-pulse-time.json
```
Every trial preserves the generated model, raw native output, solution log,
explicit status, elapsed time and water-balance checks. The aggregate is failed
if any requested trial fails. Solver failures are not redrawn or discarded.
Source, external-input, component and engine identities are recorded.

Pressure is interpolated through total head, then the extraction elevation is
removed. Water content is interpolated independently from native theta values;
it is not reconstructed from interpolated pressure through a nonlinear law.
Extraction beyond representative cell depths is rejected. The first observation
point supplies the adapter's primary pressure series; its legacy failure-depth
metadata is relabelled as extraction depth in this hydrology-only diagnostic.

## Archived numerical references

`validation.geostudio_archive.extract(path, analysis, points)` reads selected
saved results from a GSZ ZIP without running GeoStudio. Supported point records
include `x_m`, `y_m` and either:

- `archive_node`: pressure from each saved `NNN/node.csv`, with the node's actual
  coordinates checked from the supported little-endian PLY mesh layout; or
- `archive_theta_graph`: a saved `VolWaterContent` time graph. The reader resolves
  its graph ID, cache sequence, location and point cut-line from the saved analysis
  XML and requires the requested coordinate and quantity to match.

Graph titles and display units are not used to identify a physical quantity.
Pressure conversion uses 9.807 kN/m³; every reference must match the analysis
`time.csv` grid. Cached graph moisture is labelled as archived numerical output,
not experimental observation or moisture inferred from pressure. Original archive
files are read only. Callers should retain the archive and extractor hashes with
the exported reference JSON.

## Comparison

```sh
python3 -m validation.column_comparison results/column-study.json /absolute/path/archived-references.json --output results/column-comparison.json
python3 -m unittest discover -s tests -p test_column_sensitivity.py
```

The reference object contains `points`, keyed by point ID; each entry has the
original `point` mapping and a `series` of `time_h` with `theta` or
`pressure_head_m`. Comparisons require completed native trials, identical
physical inputs across the refinement matrix, matching extraction metadata,
and a native sample at each archived timestamp. A denser native series may be
compared directly against a sparser archive. For a shortened run, trim the
external archive reference to the same time window first. Bias is native minus
reference. RMSE, maximum absolute
and final differences are descriptive saved-time statistics, not uncertainty
bounds. Refinement statistics are reported separately from archive disagreement.

These comparisons cannot isolate dimensional reduction if the constitutive laws
or boundaries also differ. In particular, closed surface ponding and a reviewed
infiltration/seepage boundary need distinct accounting. Final-time agreement
between grids does not establish convergence of an earlier sharp wetting front.
The diagnostic never marks a study experimentally validated or assigns universal
acceptance thresholds.

For a zero-storage rainfall/excess-water control, see
[reviewed surface equations and verification](reviewed_surface.md). It uses the
same external study schema with `column.surface_boundary` set to
`reviewed_infiltration`, requires cell-centred heads and remains hydrology-only.
All boundary component hashes are now recorded alongside source identities.

## Synthetic wetting-front benchmark

Run the reviewed-infiltration case at three grids and two maximum time steps.
This case uses synthetic material inputs and does not require a GSZ archive.

```sh
python3 -m validation.column_sensitivity models/wetting_front_benchmark.json --cells 16 32 64 --step-divisions 240 480 --engine-seconds 120 --output results/wetting-front-benchmark.json
python3 -m validation.wetting_front results/wetting-front-benchmark.json
```

For both depths, the proposed numerical targets are 0.03 m pressure-head
difference, 0.01 m³/m³ volumetric-water-content difference and two minutes
in arrival time for 32→64 cells at 7.5 s. For 15→7.5 s at 64 cells they are
0.005 m, 0.002 m³/m³ and one minute, respectively. Arrival means the first
upward crossing of initial water content plus 0.02 m³/m³, interpolated from
one-minute outputs. The assessment also requires maximum absolute water-balance
residual at or below 1e-7 m³ in every trial. These targets apply to this synthetic
benchmark as numerical screening criteria. The 16→32 pair is descriptive.

The initial native run exceeded the pressure targets (maximum differences
0.166 m spatial and 0.0262 m temporal), while moisture and arrival-time
differences met both sets of targets. Use the normal assessment command to
report such a valid result, or add `--require-pass` to return a failing exit
status when an acceptance target is missed.

To distinguish implementation differences from discretization sensitivity, run
the same six cases with the independent Python finite-volume integrator:

```sh
python3 -m validation.wetting_front results/wetting-front-benchmark.json --independent --output results/wetting-front-independent.json
```

The report includes an independent assessment and native-versus-reference
differences at both extraction depths. Both solvers use the same discrete
constitutive and boundary laws and maximum steps. This comparison checks the
implementation and does not establish continuum accuracy. In the synthetic
case, both solvers reproduced the same pressure sensitivity (0.166 m spatial,
0.0262 m temporal).

For finer independent checks, use `--fine-grid`:

```sh
python3 -m validation.wetting_front results/wetting-front-benchmark.json --fine-grid --output results/wetting-front-fine-grid.json
```

This runs 64, 128 and 256 cells at maximum steps of 7.5 and 3.75 s.
Grid comparisons hold the maximum step fixed, and temporal comparisons
hold the grid fixed. The JSON includes both sampled histories, solver step
counts, water-balance residuals and the same case-specific acceptance targets.
The top-level assessment and `--require-pass` still refer to the original
native benchmark. Fine-grid pair statuses appear under `fine_grid.comparisons`.

In the independent run, 128→256 cells met the spatial targets at both steps
(peak pressure differences 0.0214 m and 0.0228 m). At 256 cells the 7.5→3.75 s
comparison still changed pressure head by up to 0.0197 m, above the 0.005 m
temporal target. The results reflect the benchmark's saved times and depths.

To halve the maximum time step successively at 256 cells, run:

```sh
python3 -m validation.wetting_front results/wetting-front-benchmark.json --fine-time --output results/wetting-front-fine-time.json
```

The independent solver compares 3.75→1.875 s, 1.875→0.9375 s and
0.9375→0.46875 s at the original one-minute output times. The `fine_time`
report records each pair's pressure, moisture and arrival differences and
acceptance status, as well as conservation at each step size.
The last pair met the numerical targets at both depths: peak pressure-head
difference was 0.00269 m, peak moisture difference was 0.000094 m³/m³,
and the largest arrival-time change was 0.27 s. The result applies to the
independent synthetic column at the benchmark's saved output times.

## Full archive inventory

```sh
python3 -m validation.geostudio_archive /absolute/path/project.gsz --output results/geostudio-inventory.json
```

The inventory lists all file members by saved analysis folder, including project
files, snapshots, mesh files, results tables, caches and unrecognized types.
It records each member's size and ZIP CRC. Steps with a standard
`NNN/node.csv` table are also listed. Analysis folder names are archive labels
and do not establish which analyses OHQ can reproduce. The point reader above
provides numerical interpretation for its supported variables.
