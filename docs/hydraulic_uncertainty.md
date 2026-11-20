# Hydraulic and mechanical uncertainty

## Selecting a mode

In the interface choose OHQ rainfall column, Monte Carlo, and enable **Sample hydraulic properties too**. Without that switch, the existing mechanical ensemble reuses a single pressure history. With it, every realization independently samples the configured hydraulic and mechanical inputs and runs OHQ in its own folder.

Hydraulic ranges currently support:

- `ksat_m_day`: saturated conductivity.
- `alpha_per_m` and `n`: retention-curve parameters.
- `initial_theta`: initial moisture content.

Each range specifies `min`, `max`, and `distribution`, with distribution `uniform` or `log_uniform`. A log-uniform draw samples log(parameter) uniformly between log(min) and log(max); it is not a lognormal distribution. Bounds must be valid for the column and contain the nominal input. Fixed ranges are allowed. Mechanical ranges remain independent uniform draws. No parameter correlations or spatial random fields are modelled.

The selected `column.formulation` is fixed across the ensemble. Both the legacy
and [cell-centred](cell_centred_column.md) modes use the same sampling workflow;
formulation uncertainty is not automatically mixed into parameter uncertainty.

Geometry, failure depth, rainfall, other hydraulic quantities, and boundary condition remain fixed. The total unit weight is sampled mechanically but held fixed in time for each realization; it is not derived from simulated water content. These limits must be considered when defining a physical joint distribution.

## Reproducibility and run handling

The application uses a seeded local random generator and stable parameter ordering. Each trial stores the sampled values in `realizations/<index>/parameters.json`, its state in `status.json`, and generated OHQ inputs, raw observations, and log under `hydrology/`. The final JSON also includes every sampled parameter set, minimum FS, first sampled crossing, and water-balance residual. CLI output carries an explicit running/completed/failed/cancelled state; a failed rerun replaces an old result with a failure record so a stale probability is not mistaken for the new calculation.

A maximum of 100 hydraulic solves is allowed per job. Execution is sequential within the job and supports cancellation during OHQ execution. A failed solve or invalid frictional-contact state fails the complete job explicitly. No partial probability is reported, and failed realizations are not silently dropped or redrawn. This avoids conditioning results on numerical success. Trial diagnostics remain locally available for investigation.

The nominal column specification is retained as metadata and labelled nominal; it is not presented as the actual input of all realizations. Pressure plots show pointwise median and 5–95% bands across independently simulated histories. These quantiles do not constitute one physical pressure trajectory. FS bands come from the paired mechanical and pressure inputs of each realization, not FS calculated from median pressure and median strength.

## Example and interpretation

```sh
python3 -m uncertainty.run models/hydraulic_ensemble_example.json --output results/hydraulic-ensemble.json
```

The example requests five realizations to demonstrate execution; five is far too few for a stable failure-probability estimate. Its ranges are synthetic, not calibrated or recommended for a site. Increase sample size after selecting defensible distributions and checking numerical convergence.

Sampling uncertainty and discretization error are different. The hydraulic pressure bands do not account for the unresolved transient spatial sensitivity described in [verification notes](verification.md). These capabilities support research and development, not a validated site-specific risk assessment.
