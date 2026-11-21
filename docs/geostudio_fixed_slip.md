# OHQ seepage to circular-slip stability benchmark

The offline benchmark compares the archived GeoStudio flume snapshot
`Slope Stability` at 40 minutes, slip 44, with native OHQ pressure fields.
It checks the archived slice moment ledger, replays the archived basal
pressures with Simplified Bishop, and then substitutes OHQ pressures with
the same saved slice weights, widths, angles and strength parameters.
Pressure is sampled at each saved slice base coordinate. The OHQ mapper
interpolates between soil cell centres and uses constant extension over
the half cell at a soil boundary. It rejects points outside the soil.
Pressure head is converted using 9.807 kN/m³.

The Bishop calculation supports static vertical weights, a circular fixed
surface, and constant effective friction and suction friction angles per
slice. For the flume, it uses effective friction 20.4° and suction
friction 10°. The archive uses Morgenstern–Price. The comparison therefore
tests agreement for this snapshot across these formulations. Suction is
represented by an apparent cohesion contribution below zero gauge pressure.
External loads, interslice shear, and pressure-dependent slice weights
are outside this coupled benchmark.

From the repository root, set `archive` to the original GeoStudio archive
and use the verified first-two-hour native OHQ comparison runs as inputs.

```sh
python3 -m validation.geostudio_fixed_slip "$archive" \
  results/geostudio-native-2h-coarse.json results/geostudio-native-2h-fine.json \
  --output results/fixed-slip-comparison.json
python3 -m validation.geostudio_slip_uq results/geostudio-native-2h-coarse.json \
  results/fixed-slip-comparison.json --output results/fixed-slip-uq.json \
  --samples 4 --seed 42 --workers 2
```

The comparison also screens 36 explicit crest-to-toe circular candidates
using the archived ground profile and assumed uniform unit weight of
12 kN/m³. Rejected candidates and their reasons are saved. Compare the
minimum over the accepted candidates at 30 and 60 slices per arc. This
screening uses a restricted search domain and differs from the archived
GeoStudio slip search. The UQ pilot reruns native OHQ for conductivity
draws from an illustrative log-uniform range of 0.8–1.2 times nominal and
uses the same accepted candidates for every realization. The four-draw
quantiles are a numerical workflow check. The benchmark script records
the fixed surface and candidate-envelope results separately.
