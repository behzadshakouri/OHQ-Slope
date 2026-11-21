# Matched GeoStudio circular search

Use a working copy of the original flume archive and keep its saved
`Transient Seepage` parent solution. Compare the first two hours at the
25 saved states, from 0 to 120 minutes in 5-minute steps. Use a separate
Simplified Bishop analysis for each prescribed circle so every circle
has its own FS history.

## Stability settings

Use the original ground profile (x, elevation in metres):
(0, 1.4), (0.5, 1.4), (1.6, 0.3), (2, 0.3). Use left-to-right movement,
static conditions, uniform unit weight 12 kN/m³,
effective cohesion 19.3 kPa, effective friction 20.4°, and constant
suction friction 10°. The OHQ-side weight convention is width × soil
height at slice midpoint × unit weight. Compare actual exported widths
and weights, since a 60-slice setting by itself does not guarantee
identical slice boundaries or weight integration. Keep weight fixed
in time for the comparison and use the parent pressure results.
The OHQ replay uses signed pressure in kPa with zero pore-air gauge
pressure and no external loading or ponded-water load. Check the
GeoStudio load and material settings against those assumptions.

Use the center, radius, entry and exit in `circles.csv`. If representing
the surface as a fully specified polyline, use the dense points in
`arc_points.csv` and set its moment axis to that circle's center. That
file includes one tangent extension beyond each ground intersection.
Check the resulting surface against the exact circle. Keep optimization
off so the same surface is evaluated at each time. Start at 60 slices.
For the finalist, repeat at 30 and 120 slices and record the actual
slice boundaries. The documented GeoStudio options and moment axis
are described in the SLOPE/W modeling guide, section 4.4.
[Seequent SLOPE/W modeling guide](https://files.seequent.com/PDFs/Geostudio-Stability%20Modeling-Oct2022.pdf)

## Export and compare

1. Export FS and each slice's base midpoint, width, weight, basal
   inclination, and pressure for each circle and saved time. Retain the
   raw solver exports and the GeoStudio build number.
2. Populate the supplied CSV templates. Use kPa and hours, positive-downslope base
   angle in degrees, and weight in kN per metre of slope width. Keep
   GeoStudio's actual slice geometry. If it produces a different number
   of slices, retain its raw slice export separately and use the FS
   template for the direct run comparison.
3. Compare fixed-circle FS with `bishop_with_archived_pressure` in
   `bishop_fs.csv`. Use `slices.csv` and `slice_pressures.csv` to
   diagnose gaps. Then compare with `bishop_with_ohq_pressure` to
   quantify the effect of changing the pressure source.
4. Compare the winning circle and near ties at each time. Treat any
   expanded-search candidate selected by either pressure field as an
   additional challenge surface in GeoStudio before declaring the
   search aligned.

The input settings and archived-pressure replay are reproducible with
`python3 -m validation.geostudio_matched_search ARCHIVE NATIVE BASELINE OUTPUT`.
Use the exact fine-grid native JSON and preceding benchmark JSON to
satisfy the input hash check. The script samples the archived linear
triangles and bilinear quadrilaterals and applies the same Simplified
Bishop implementation to the two pressure fields. A new GeoStudio
stability solve is a separate check of method and discretization.

Once the FS template is populated, run
`python3 -m validation.geostudio_compare_exports bishop_fs.csv geostudio_fs.csv`
to report FS differences and winning circle IDs at every saved time.

### First-run check for C01

The updated checker accepts a C01-only export. Copy the raw SLOPE/W slice
values into the normalized template, numbering slices from left to right.
Retain the raw files for checking slice positions and angle convention.
Use the original 25 elapsed times in hours without rounding them in the
CSV. A different number or arrangement of slices requires inspection
before differences can be attributed to the pressure or stability solver.

```sh
python -m validation.geostudio_compare_exports bishop_fs.csv populated_geostudio_fs.csv \
  --circle C01 --count 60 --slice-export populated_geostudio_slices.csv \
  --slice-geometry slices.csv --slice-pressures slice_pressures.csv
```

The slice report gives bias, RMSE, maximum absolute difference, and the
time and slice number of the largest difference for each field. Slice
differences are GeoStudio export minus replay. FS differences retain
the signs shown in their output field names.
