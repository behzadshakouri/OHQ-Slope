# Measured flume data intake

Use one event and commit to distinct calibration and holdout sensors
before fitting. Preserve the raw logger exports. This adapter uses one
measured rainfall schedule uniformly over the modeled horizontal area.
Convert accumulated rain to interval-average intensity before intake.
Missing rainfall intervals must be resolved from the logger record.
Represent confirmed dry intervals with zero intensity.

Provide a valid OHQ section scenario and the four input files described
below. Coordinates and head elevations are in metres in the same local
datum as the section. The current native observation operator samples
cell centres, so choose an appropriate coordinate tolerance before
calibration. The audit records the distance for each sensor.

| File | Required content |
| --- | --- |
| `metadata.json` | Event ID, documented common clock origin, separate logger time units and signed offsets in hours, units and pressure convention, water unit weight, coordinate tolerance, and native MCMC settings. |
| `rainfall.csv` | `start,end,intensity`. Use a continuous sequence covering the modeled event. Supported intensity units are mm/h, mm/min and m/s. |
| `pressure.csv` | `sensor_id,time,value`. Times must increase per sensor. Supported time units are s, min and h. |
| `sensors.csv` | `sensor_id,role,x_m,elevation_m,column,layer,sigma_m`. Use zero-based columns from left to right and layers from top to bottom. Set role to `calibration` or `holdout`. |

The normalized elapsed time is input time converted to hours plus the
logger offset. The offset must come from known clock alignment. The tool
does not infer it. Use gauge pressure referenced to atmosphere or signed
positive suction. If providing total head, use metres in the same
vertical datum as the sensor coordinates. The tool computes pressure
head by subtracting sensor elevation. Resolve unknown sensor zeros and
pressure conventions before intake.

```sh
python3 -m validation.flume_intake scenario.json metadata.json rainfall.csv pressure.csv sensors.csv normalized
```

The output includes the measured-rainfall scenario, the native MCMC
calibration settings, the independently indexed holdout, and an audit
with input hashes. Review the normalized event clock, rainfall depth,
pressure datum and sensor distance audit before calibration. Use
`uncertainty.section_mcmc` for native calibration as described in
[the scenario guide](section_scenario.md). Check chain convergence using
the calibration sensors. Keep the holdout sealed while selecting model
parameters and configuration.

After fixing a conductivity or retained draw, run the normalized scenario
with that conductivity. Use the resulting native forward JSON with
the saved holdout. For example:

```sh
python3 -m hydrology.section fitted_scenario.json --output forward.json
python3 -m validation.flume_intake --evaluate forward.json normalized/holdout.json holdout_scores.json
```

The holdout scorer uses the registered cell centres and interpolates
in time within the saved forward results. It reports signed residuals,
bias and RMSE per held-out sensor. It scores an individual forward run.
Posterior predictive coverage requires propagation across retained draws.

The accompanying synthetic example demonstrates the input format,
normalization, and holdout scoring using a nominal native forward run.
