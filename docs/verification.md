# Independent flow verification and remaining grid sensitivity

## Analytical small-amplitude diffusion check

The new benchmark uses the existing OHQ unsaturated Soil component in a closed, horizontal column. All representative elevations are equal, removing gravity. Soil-to-soil links, retention, conductivity, and water storage remain active. This tests more than water bookkeeping, while retaining an analytical reference that is independent of OHQ's time integrator.

The mixed flow equation without sources is

```text
C(psi) * dpsi/dt = d/dx [ K(psi) * dpsi/dx ]
```

For a small perturbation about uniform psi0, the leading-order equation is `dpsi/dt = D*d²psi/dx²`, where `D=K(psi0)/C(psi0)`. With no-flow ends and an initial cosine disturbance:

```text
psi(x,t) = psi0 + a*cos(pi*x/L)*exp(-D*pi²*t/L²)
```

This satisfies the linearized equation and the zero-gradient end conditions directly. The benchmark computes capacity analytically by differentiating the van Genuchten retention curve and conductivity using its Mualem relationship. Cell locations are the centres of equal horizontal control volumes. There is no rainfall or surface boundary in this test.

The demonstration uses L=1 m, psi0=−1 m, amplitude a=0.001 m, duration=0.2 days, and maximum time step=0.0002 days. The derived diffusivity is approximately 0.09428 m²/day. The finite perturbation introduces a nonlinear remainder of order a²; this is not an exact solution of the full nonlinear rainfall problem.

Observed maximum pressure errors at the final time were approximately:

| Cells | Maximum error (m) | Error relative to initial amplitude |
|---|---:|---:|
| 8 | 2.05e-6 | 0.205% |
| 16 | 6.49e-7 | 0.0649% |
| 32 | 3.05e-7 | 0.0305% |

Reproduce the check with:

```sh
python3 -m validation.diffusion --output results/diffusion-check.json
```

Its test requires decreasing error on refinement and a fine-grid error below 0.2% of the initial amplitude. That tolerance is specific to this benchmark. It is not a universal hydrologic accuracy bound. General diffusion-equation verification by comparison with analytical solutions is also described in the [USGS diffusion model report](https://pubs.usgs.gov/publication/wri894027); the cosine reference here is derived above.

## Independent nonlinear fixed-flux infiltration comparison

`validation/infiltration.py` solves a separate nonlinear Richards problem with gravity. Depth `x` and flux `q` are positive downward:

```text
q = K(theta) * (1 - dpsi/dx)
dtheta/dt = -dq/dx
q(0,t) = 0.02 m/day; q(1 m,t) = 0
psi(x,0) = -1 m
```

The test lasts 0.2 days and compares complete pressure profiles at 0.05, 0.1 and 0.2 days. Its van Genuchten–Mualem parameters match the diffusion example. The [USGS description of Richards flow](https://pubs.usgs.gov/tm/2006/tm6a19/section3.html) gives the vertical water-content equation and nonlinear constitutive relationships; the numerical reference here integrates that equation directly, rather than using the kinematic-wave approximation described later in that source.

The independent reference uses conservative cell-centred finite volumes, arithmetic mean interface conductivity, and explicit second-order Heun integration. A local `0.15*dx²/max(K/C)` step restriction is evaluated at the current state and predictor; no water-content clipping is applied. It rejects states outside the unclipped unsaturated range. Internal interface fluxes cancel in the water ledger. This is a numerical reference, not an exact analytical solution or a universal stability guarantee.

The reference has 128 cells. Its 64-to-128-cell maximum profile difference is approximately 5.54e-5 m; halving its time-step safety factor changes pressure by 1.37e-8 m. These are empirical resolution checks, not rigorous error bounds. OHQ uses its existing soil-to-soil connector, whose maximum-Se conductivity differs from the reference's arithmetic mean; the discrete methods need not agree on a coarse mesh.

| OHQ cells | Maximum pressure difference from 128-cell reference (m) |
|---|---:|
| 8 | 0.00739 |
| 16 | 0.00513 |
| 32 | 0.00297 |

Halving the 32-cell OHQ step from 0.0002 to 0.0001 days changes the saved profiles by approximately 2.15e-5 m. Both implementations conserve water to better than 1e-12 m in this demonstration. The regression check requires decreasing OHQ errors and a 32-cell maximum difference below 0.004 m at the three saved times. It also checks independent-reference spatial/time sensitivity and conservation.

```sh
python3 -m validation.infiltration --output results/infiltration-check.json
```

The output records profiles, resolution differences, conservation residuals, benchmark-source hash, and pinned engine/build provenance. Generated inputs and raw engine observations remain beside the output in its `_files` directory.

This benchmark applies the rainfall flux directly to the first soil volume using an OHQ inflow time series. It has no surface-water block or ponding. To compare the same cell-centred discretization, benchmark-only block elevations place OHQ's head references at cell centres. The production adapter's top-reference convention is unchanged. All compared pressures remain negative, so saturated compressibility, surface ponding, and positive-pressure FS coupling are outside this test's scope.

## Ponding, saturation, and a remaining boundary/discretization gap

`validation/ponding.py` extends verification through surface ponding and the positive-pressure storage branch. A 0.5 m sealed column starts at theta=0.30, receives 40 mm/h for 3 h, then drains internally for 3 h. Other soil parameters are the app defaults. The failure-plane pressure is compared at 0.25 m depth every 0.25 h. This is a synthetic diagnostic, not the experimental case.

The independent solver uses conservative cell-centred finite volumes, arithmetic interface conductivity, backward Euler, a tridiagonal Newton solve with line search, and explicit failure if step reductions cannot converge. Its surface reservoir satisfies:

```text
dh/dt = rainfall - infiltration; h >= 0
q_top = min(rainfall + h_old/dt,
            Ksat*(h_new - psi_first + dx/2)/(dx/2))
```

This is a discrete water-availability/ponded-head boundary. It has no surface-depth smoothing. The [HYDRUS boundary documentation](https://www.pc-progress.com/en/OnlineHelp/HYDRUS3/WaterFlowBoundaryConditions1.html) describes the underlying surface-reservoir balance between rainfall and infiltration; this implementation is independent and is not a HYDRUS run.

To isolate numerical and boundary effects, both solvers use the same **documented OHQ storage law**. For raw effective saturation above 0.999, OHQ clips its suction/conductivity saturation and adds excess pressure. Consequently, on this branch:

```text
theta(psi) = theta_r + 0.999*(theta_s-theta_r)
             + Csat*(psi-psi_transition)
Csat = (theta_s-theta_r)*specific_storage/theta_s
```

This is not an independent validation of that constitutive choice. Theta above nominal theta_s represents compressible excess storage, not additional pore-volume saturation.

The independent reference uses 128 cells and a maximum 0.000125-day step. Its 64-to-128-cell maximum failure-pressure difference is 0.00345 m; halving the reference step changes pressure by 0.00122 m. These quantify unresolved reference error rather than providing an exact transient solution. Water balance stays within 2e-8 m³. Both solvers transition from negative to positive pressure and finish above nominal theta_s.

| Production OHQ cells | Maximum pressure difference from reference (m) | Final pressure difference (m) |
|---|---:|---:|
| 8 | 0.1205 | 0.0001362 |
| 16 | 0.0712 | 0.0000681 |
| 32 | 0.0443 | 0.0000341 |

At 32 cells, maximum surface-depth difference is about 0.000258 m. Conserved water and close final water levels do **not** establish transient pressure accuracy. The remaining 4.4 cm pressure difference exceeds the reference refinement differences.

There is also an exact late hydrostatic check. With `theta=b+Csat*psi`, the continuum sealed-column equilibrium is:

```text
h_final = (initial_water + rainfall_depth - b*L - Csat*L²/2)
          / (1 + Csat*L)
psi(x) = h_final + x
```

Here `h_final` is approximately 0.06870877 m. The production top-reference grid has a calculable surface-depth offset `Csat*L²/[2*N*(1+Csat*L)]`. Regression tests check that offset, mass conservation, positive pressure, excess storage, and decreasing transient differences. They deliberately do not label the transient model validated.

The inspected production connector uses `Ksat*(head_surface-head_soil)/(dx/2)` multiplied by `h/(h+0.001)` for nonnegative surface depth, while the first soil head is referenced at the block top. The independent boundary uses a cell-centred head and water-availability constraint. These differences, plus the interior maximum-Se conductivity rule, are plausible contributors to the transient gap; this experiment does not separate their individual effects. Production equations and the pinned OHQ dependency are unchanged.

```sh
python3 -m validation.ponding --output results/ponding-check.json
```

The JSON output records reference profiles, grid/time sensitivity, production differences, the analytical final water level, and source/engine provenance. Resolving the transient gap remains necessary before experimental-case interpretation.

A [controlled eight-variant study](ponding_diagnosis.md) now separates head
placement, conductivity, surface smoothing, and time integration. At 32 cells,
matching the production discrete laws reduces OHQ/reference disagreement to
about 0.001 m with a quarter-sized OHQ step, while the difference from the
alternative formulation remains about 0.047 m. The formulation gap decreases
under independent 32/64/128-cell refinement but is not eliminated.

## Original rainfall grid sensitivity is still unresolved

The smooth diffusion check passes, but the rainfall-column wetting transition remains sensitive to block size. The earlier 16-to-32-cell pressure difference was about 0.13 m, despite much closer late hydrostatic states. Conservation and a smooth-flow benchmark do not establish convergence of a sharp nonlinear wetting front.

As an investigation, the generated Soil head expression was also changed locally to `bottom_elevation+depth/2+pressure_head`, with pressure mapping shifted to cell centres. This improved agreement of final hydrostatic pressure between 16 and 32 blocks to about 2e-8 m, but the largest transient difference remained about 0.24 m. Consequently, the production adapter retains the documented upstream top-reference convention; a coordinate shift alone is not adopted as a validated transient correction. No OHQ source change was made.

Reproduce the production-convention rainfall comparison with:

```sh
python3 -m validation.refinement --output results/refinement.json
```

The diagnostic explicitly does not declare convergence. The ponding comparison above now measures the production-boundary discrepancy, while further spatial refinement and controlled tests of interface conductivity and surface discretization remain necessary. Do not interpret pressure bands or failure timing as free of discretization error.
