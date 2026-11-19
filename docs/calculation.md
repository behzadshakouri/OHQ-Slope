# Calculation specification

## Reference model

The implemented factor of safety is

```text
normal_stress = gamma * z * cos(beta)^2
pore_pressure = 9.81 * max(pressure_head, 0)
driving_stress = gamma * z * sin(beta) * cos(beta)
FS = [c + (normal_stress - pore_pressure) * tan(phi)] / driving_stress
```

`c` is effective cohesion in kPa, `gamma` is total unit weight in kN/m³, `z` is vertical failure depth in metres, and `beta` and `phi` are supplied in degrees and converted to radians internally. Water unit weight is 9.81 kN/m³. Head is supplied at the failure plane. The assumed soil and failure plane are uniform and parallel to the ground surface.

Negative head provides no suction strength. Unit weight is fixed for each realization and does not change with head. No seismic inertia, roots, deformation, erosion, layered stress integration, or cyclic strength loss is included. If pressure exceeds total normal stress, the entire job fails explicitly because this frictional contact model is outside its domain. Such a run is not classified as stable or silently removed from a probability estimate.

The displayed slope section is a schematic, not generated model geometry. Time is an input label in hours; FS is evaluated independently at each supplied pressure-history row. No water balance or hydrologic simulation is performed by this mode.

## Mechanical uncertainty

In ensemble mode, each of the five mechanical parameters is sampled independently from its supplied uniform bounds, once per realization. It is held constant through that realization's pressure history. Fixed bounds are permitted. This is a mechanical uncertainty demonstration, not a representation of spatial random fields or correlated measured material properties. All realizations share the prescribed pressure history.

The seeded standard-library random generator makes repeated runs reproducible in the supported environment. The server stores requests, source hashes, dependency provenance, job status, and results. There is no model discrepancy or observation likelihood in this initial mode.

At each time, the code reports empirical 5th, 50th, and 95th percentiles using linear interpolation between sorted samples. It also computes the minimum FS within each realization over supplied times. Event instability frequency is the fraction of those minima below 1. This is a sampled-time estimate: a pressure peak between supplied rows may be missed. First crossing means first supplied time with FS below 1; `null` means no crossing observed during the history.

Monte Carlo standard error is the independent Bernoulli approximation `sqrt(p*(1-p)/N)`. It is not a confidence interval and returns zero at observed frequencies zero and one; that does not establish certainty. No rare-event or correlated-sample correction is implemented. Deterministic runs report a threshold indicator rather than an inferred probability.

## Bounds and workload

The application imposes finite input and workload limits: at most 10,000 realizations, 500 increasing pressure rows, and one million realization-time evaluations per job. Mechanical bounds are numerical guardrails, not recommended ranges for a site. One worker processes up to eight active/queued jobs, each in a separate directory. A failed calculation has no downloadable result.

## Verification and remaining work

Tests check the dry cohesionless limit `tan(phi)/tan(beta)`, an independent 45-degree force balance, pressure reduction of FS, omitted suction strength, domain failures, seeded sampling, and event-frequency aggregation. These are implementation checks, not field validation. OHQ hydrologic verification, pressure mapping, discretization checks, and external stability comparisons remain pending.
