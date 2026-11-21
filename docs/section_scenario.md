# Native 2D seepage scenarios

Select **Native 2D seepage** in the app, edit the loaded example JSON, and
run it. The results show a selectable pressure probe and water-budget
diagnostics. The run download includes the submitted scenario, the pressure
and moisture fields, and native model provenance.

From the repository root:

```sh
python3 -m hydrology.section models/seepage_2d_example.json --output results/section.json
```

The example reproduces the four-column stepped-slope benchmark. Its final
runoff and seepage volumes are 0.53025 L and 0.24758 L per metre out of plane.
The generated `section.ohq` and rainfall inputs are in the run's hydrology
folder or the CLI's adjacent `*_files` directory.

## Scenario fields

| Field | Meaning |
|---|---|
| `width_m`, `cell_height_m` | Total horizontal width and common cell height. All columns have equal width and a sealed floor at elevation zero. |
| `materials` | Named soil properties. Each material specifies `ksat_m_day`, `alpha_per_m`, `n`, `theta_res`, `theta_sat`, `specific_storage_per_m`, `pore_connectivity`, and one of `initial_theta` or `initial_pressure_head_m`. |
| `columns` | Ordered from left to right. Each column supplies a top-to-bottom `materials` array and a `rainfall` interval array. Intervals use `start_h`, `end_h`, and `intensity_mm_h`. |
| `boundaries` | `surface` is `closed_ponding`, `reviewed_infiltration`, or `routed_runoff`. Set `routing_slope` for the stock runoff connector and select right boundary and exposed riser discharge with `toe_seepage` and `riser_seepage`. The left wall and base are sealed. |
| `duration_h`, `solver_step_h`, `output_interval_h` | Simulation duration, maximum native time step, and output spacing. |
| `probes` | A mapping from names to `x_m` and `elevation_m`. Probe interpolation requires bracketing soil-cell centres. |

The grid supports descending or level surfaces, 2–32 horizontal columns,
and at most 300 active cells. Soil zones can change by layer and by column.
Horizontal interfaces follow the pinned OHQ connector's averaging rule.
The model uses stepped geometry and a unit width normal to the section.
The analysis evaluates seepage. The infinite-slope calculation is a
separate app mode.

The job API accepts `{"analysis":"seepage_2d","section":{...}}` at the existing
`POST /api/jobs` endpoint.

## Dashboard uncertainty and MCMC

Choose **2D uncertainty propagation** to set hydraulic ranges, the number of
realizations, and a seed. The dashboard plots the median and pointwise 5–95%
pressure-head range at each probe.

Choose **2D conductivity calibration (MCMC)** and enter calibration settings
using the observation schema below. Each job fits one material's conductivity.
The result displays both native chain traces through the chain selector, and
the run JSON includes the retained samples and conductivity summary. Assess
convergence independently before using the samples for scientific inference.

The server discovers the native executable at `build/ohq-mcmc/OHQ-MCMC`.
For a different path, set `OHQ_MCMC_BINARY` to that executable before starting
the server. The forward OHQ console is also required. The dashboard accepts
up to 2,000 MCMC samples and stops the native sampling process after 15
minutes. Each run writes its native inputs and log under its job directory.

## Forward uncertainty

Each draw runs the same native solver with new material inputs. The results
include the draws and pressure-head quantiles at each probe. A ranges file
maps a material name to parameter ranges, for example:

```json
{"soil":{"ksat_m_day":{"min":0.4,"max":0.6,"distribution":"log_uniform"}}}
```

```sh
python3 -m uncertainty.section models/seepage_2d_example.json ranges.json --samples 20 --seed 42 --output results/section-ensemble.json
```

Supported independent ranges are saturated conductivity, alpha, n, and
explicitly specified initial volumetric water content. The sampler reuses
the existing uniform and log-uniform distributions.

## Export to native OHQ-MCMC

Provide a calibration JSON with `material`, `min_ksat_m_day`,
`max_ksat_m_day`, `samples`, `burn_in`, and `observations`. Each
observation specifies zero-based `column` and `layer` indices, positive
`sigma_m`, and a `series` of increasing `time_h` and `pressure_head_m`
pairs. Measurements are interpreted at cell centres in this export. The
export binds the same conductivity parameter to a named material's cells
and its seepage links, converts observation time from hours to days, and
configures two chains with the native log-normal prior option. The two
conductivity inputs parameterize the prior; the native log-normal density
permits positive values outside that input interval.

A series in `observations` has this format:

```json
{"column":0,"layer":1,"sigma_m":0.01,"series":[
  {"time_h":0,"pressure_head_m":-0.1},
  {"time_h":0.5,"pressure_head_m":-0.08}
]}
```

```sh
python3 -m uncertainty.section_mcmc models/seepage_2d_example.json calibration.json --output-dir results/section-mcmc
cd results/section-mcmc
OHQ-MCMC calibration.ohq .
```

Build OHQ-MCMC from the pinned submodule's
`terminal/OHQ-MCMC/OHQ-MCMC.pro` with Qt 6 qmake and the same native math
libraries as the forward console. A synthetic four-cell run with 24 samples
and 4 burn-in steps verified the export, OHQ executable, and chain output.
Use measured heads, justified error scales, and convergence checks for
scientific calibration.
