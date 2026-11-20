# Offline hydrology-only column sensitivity

`validation.column_sensitivity` runs a grid/time matrix from an external JSON
study. Case geometry, extracted archive data, fitted parameters and research
interpretation remain outside the software repository. No FS is evaluated.

An external study supplies `formulation_role: "hydrology_only"`, a complete
`column` specification accepted by the normal adapter, and a `points` list.
Each point needs a unique `id` and `vertical_depth_m`. Additional coordinate
and provenance fields are preserved, allowing the same hydrology to be sampled
at several observation depths without equating those depths to slip surfaces.

```sh
python3 -m validation.column_sensitivity /absolute/path/study.json --cells 16 32 64 --step-divisions 240 480 --engine-seconds 600 --output results/column-study.json
```

The existing grid, physical-input and time-step bounds are retained. The only
runtime exception is an explicit offline engine allowance of 1–900 seconds,
with a process guard five seconds longer; web/API budgets are unchanged.
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
and matching saved times. Bias is native minus reference. RMSE, maximum absolute
and final differences are descriptive saved-time statistics, not uncertainty
bounds. Refinement statistics are reported separately from archive disagreement.

These comparisons cannot isolate dimensional reduction if the constitutive laws
or boundaries also differ. In particular, closed surface ponding and a reviewed
infiltration/seepage boundary need distinct accounting. Final-time agreement
between grids does not establish convergence of an earlier sharp wetting front.
The diagnostic never marks a study experimentally validated or assigns universal
acceptance thresholds.
