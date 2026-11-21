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
