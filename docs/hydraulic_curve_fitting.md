# Offline hydraulic table representation

`validation.hydraulic_fit` evaluates whether archived hydraulic tables can be
represented by the pinned OHQ Soil storage and conductivity laws. It does not
calibrate observations, set uncertainty distributions, or install parameters in
the app. Case-specific tables and research results remain outside this repository.

Input CSV columns are `function`, `pressure_magnitude_kPa`, `value`, `value_unit`.
Use `retention` with `m3/m3` and `conductivity` with `m/s`. Each table needs at
least five increasing, nonnegative suction magnitudes with positive,
nonincreasing values. Extra provenance columns are permitted. Input is read only.

```sh
python3 -m validation.hydraulic_fit /absolute/path/hydraulic_curves.csv --output results/hydraulic-fit.json
```

This optional diagnostic requires NumPy and SciPy. The app and standard-library
checks do not require these packages. The measured run used NumPy 1.21.5 and
SciPy 1.8.0 with Python's user packages disabled to avoid a conflicting local NumPy.
Each result records the actual library versions and optimization settings.

## Equations and objective

Suction magnitude is converted to negative pressure head using 9.807 kN/m³.
The evaluator inverts the pinned OHQ storage law: van Genuchten below Se=0.999,
then its compressible excess-storage branch, with fixed specific storage
0.01/m. Conductivity uses the clipped Se and the pinned Mualem expression.
Requests beyond the dry clipping/head-cap range are flagged as noninvertible;
the returned limiting state is not a valid pressure prediction there.

The joint objective is mean squared water-content residual divided by the
squared theta scale plus mean squared log10 conductivity ratio. Means are
computed separately for the two tables. The theta scales 0.005, 0.01 and 0.02
are diagnostic weighting choices, not observation standard deviations. A fourth
joint fit fixes connectivity L=0.5. Separate retention and conductivity fits
help distinguish individual representability from a shared-parameter compromise.
Unfitted parameters in separate fits are marked as fixed, and only the fitted
curve's residuals are reported.

Alpha, n, Ksat and connectivity use existing app bounds. Residual water content
is bounded below the smallest tabulated water content; saturated water content
uses a table-informed lower bound and an upper bound below one. Exact bounds
are saved with each fit. Specific storage is assumed, not independently
identified. Bound hits must be considered when interpreting any candidate.

Twelve deterministic starts use seed 20261120. Ksat and alpha are optimized in
log space; all other parameters use physical coordinates. Every fit reports the
best objective, all start objectives, optimizer termination, bounds hit and
pointwise predictions. Optimization completion does not imply physical or
statistical acceptance. Inspect dry-range flags, systematic residuals, bounds,
weight sensitivity and initial-state consistency before using a fit.

## Verification

```sh
python3 -m unittest discover -s tests -p test_hydraulic_fit.py
OHQ_FIT_OPTIMIZER_TEST=1 python3 -m unittest discover -s tests -p test_hydraulic_fit.py
```

Standard checks compare the evaluator with the independent storage implementation
on unsaturated and compressible branches, check conversion and dry-floor flags,
and reject invalid input units/order/values. The opt-in SciPy test recovers six
known parameters from exact synthetic curves. This verifies optimization behavior
for that identifiable synthetic case; it does not establish uniqueness or accuracy
for observed curves. No native engine or application behavior is modified.
