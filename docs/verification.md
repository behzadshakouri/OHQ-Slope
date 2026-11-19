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

## Rainfall grid sensitivity is still unresolved

The smooth diffusion check passes, but the rainfall-column wetting transition remains sensitive to block size. The earlier 16-to-32-cell pressure difference was about 0.13 m, despite much closer late hydrostatic states. Conservation and a smooth-flow benchmark do not establish convergence of a sharp nonlinear wetting front.

As an investigation, the generated Soil head expression was also changed locally to `bottom_elevation+depth/2+pressure_head`, with pressure mapping shifted to cell centres. This improved agreement of final hydrostatic pressure between 16 and 32 blocks to about 2e-8 m, but the largest transient difference remained about 0.24 m. Consequently, the production adapter retains the documented upstream top-reference convention; a coordinate shift alone is not adopted as a validated transient correction. No OHQ source change was made.

Reproduce the production-convention rainfall comparison with:

```sh
python3 -m validation.refinement --output results/refinement.json
```

The diagnostic explicitly does not declare convergence. An independent nonlinear infiltration benchmark, further spatial refinement, and examination of interface conductivity and surface discretization remain necessary. Do not interpret pressure bands or failure timing as free of discretization error.
