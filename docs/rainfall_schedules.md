# Repeated and variable rainfall

The browser, job API and command-line workflow support an optional
`column.rainfall_schedule`. Existing single-pulse inputs retain their behavior.
In the browser choose **Repeated or variable rainfall** under **Rainfall pattern**,
then enter one row per interval: start hour, end hour, intensity in mm/h.

JSON example (within a complete column specification):

```json
"rainfall_schedule": [
  {"start_h": 0.5, "end_h": 1.0, "intensity_mm_h": 40},
  {"start_h": 1.5, "end_h": 2.5, "intensity_mm_h": 20}
]
```

Omit `rainfall_mm_h` and `rain_duration_h` when using a schedule, or set both to
zero. Combining a schedule with nonzero single-pulse fields is rejected rather
than choosing one silently. Normalized requests store those pulse fields as zero
and preserve the explicit schedule. An empty list means no rain. Omitting the
schedule entirely retains the original single pulse from time zero.

Intervals must be ordered and nonoverlapping, with finite numeric values:
`0 <= start_h < end_h <= duration_h` and `0 <= intensity_mm_h <= 200`.
Adjacent intervals may change intensity without a dry gap. Up to 100 intervals
are allowed; booleans, unknown row fields and malformed intervals are rejected.
Intensity is a vertical rainfall depth rate over the column's 1 m² horizontal
area, not an automatically projected flux on a sloping face.

## Native forcing and conservation

Each interval denotes constant intensity on `[start_h,end_h)`; rain is zero in
unspecified gaps. The adapter explicitly fills leading, interior and trailing
zero-rain intervals and writes native precipitation bins as:

```text
start_day, end_day, total_depth_metres
```

The third value is `intensity_mm_h * (end_h-start_h) / 1000`, not a rate.
The pinned precipitation source preserves steps in its rate representation and
integrates rainfall over each solver step. This supports switches between native
steps, without a user-created ramp or an equivalent-duration replacement pulse.
No engine source or JSON component changes are needed.

Water-balance expectations use the exact cumulative interval integral at every
native observation time. Results record the total depth, full wet/dry intervals,
convention and original normalized specification. Job provenance includes the
rainfall adapter hash. Hydraulic ensembles retain one fixed rainfall schedule
across realizations; rainfall uncertainty is not implemented.

The output grid is unchanged. Schedule boundaries are not automatically added
to displayed FS samples. Pressure transients still need time/grid refinement;
exact forcing volume does not establish accurate failure timing.

## Run and verify

```sh
python3 -m uncertainty.run models/repeated_rainfall_example.json --output results/repeated-rainfall.json
python3 -m validation.rainfall_schedule --output results/rainfall-schedule.json
python3 -m unittest discover -s tests -p 'test_rainfall*.py'
```

The example is synthetic: a 0.5 m, eight-cell column with four variable intervals,
including a delayed start, an adjacent intensity switch, dry gaps and rain ending
at the final time. Its total depth is 48.69 mm. It is not the experimental flume.

Native tests independently integrate this schedule and compare total water at
every native output in both hydrologic formulations, with a 1e-8 m³
case-specific tolerance. Unit checks cover schema errors, empty schedules,
backward compatibility and interval-depth conversion. The HTTP check submits a
schedule, retrieves it with the result and provenance, and rejects overlap.
The JavaScript parser check rejects blank numbers rather than converting them
silently to zero. These checks do not replace browser visual inspection.

The offline diagnostic additionally compares sealed and unit-gradient cases
against the independent cell-centred solver at maximum steps 1/240 and 1/480 h.
Its forcing is constructed independently and its steps stop at forcing events.
It writes complete native/reference results, source hashes and explicit status
under ignored `results/`.

At matching steps, the measured maximum cell-centred failure-head discrepancy
is about 4.35e-5 m (1/240 h) and 5.32e-6 m (1/480 h), for either base. The
corresponding full-profile differences are 1.30e-4 and 2.29e-5 m. Native balance
residuals are below 1.8e-13 m³; independent residuals are below 1.2e-10 m³.
Halving the native step changes failure head by about 0.000815 m. These values
apply to saved 0.05-hour outputs in this synthetic case, not a universal accuracy
threshold or experimental validation.
