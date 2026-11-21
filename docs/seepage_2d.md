# 2D saturated seepage reference

The reference uses cell-centred finite volumes on a rectangular grid with
unit out-of-plane width. It solves for total head H and reports
pressure head H − z and face-normal Darcy fluxes. The conductivity tensor is
diagonal in the grid coordinates. The steady interface accepts face-wise
prescribed head on the outer boundaries. Unspecified faces are impermeable.
Interior fluxes use centre-to-centre gradients. A prescribed outer head is
one half-cell away from its adjacent centre.

## Steady verification

```sh
python3 -m validation.seepage_2d --output results/seepage-2d.json
```

The anisotropic manufactured solution is

```text
H = H0 + g z + A cos(π x / L) sinh(k z) / sinh(k D)
k = (π / L) sqrt(Kx / Kz)
qx = −Kx ∂H/∂x
qz = −Kz ∂H/∂z
```

Here L and D are the domain width and height. Differentiating shows that
Kx Hxx + Kz Hzz = 0, and the side fluxes vanish. Setting A to zero recovers
uniform 1D vertical flow. The report checks heads, lateral and vertical face
fluxes, integral throughput, local balance, and grid refinement. It includes
the finest numerical field. The finest 64 × 32 case has a 0.139 mm maximum
head error and an 8.97 × 10⁻⁶ m/h maximum lateral-flux error.

## Transient saturated rainfall and seepage outlet

```sh
python3 -m validation.seepage_2d --transient --output results/seepage-2d-transient.json
```

The saturated reference adds backward-Euler storage, Sₛ Δx Δz (Hⁿ⁺¹ − Hⁿ)/Δt.
The caller supplies a constant rainfall rate over each step as imposed
infiltration. On selected right faces the potential atmospheric outlet head
is the face-centre elevation z. Outlet flux per unit face area is
Kx max(Hcell − z, 0)/(Δx/2). An active-set solve imposes atmospheric head
on discharging faces and zero flux on closed faces. The saturated step rejects
negative cell pressure beyond roundoff.

The synthetic case applies a pulse of 35 mm/h to a 2 × 1 m domain, with
the upper half of the right boundary eligible to discharge. It checks
a single-cell analytical opening limit, one-way discharge, cumulative
water balance, and time-step refinement. Both balances use the unit width,
so boundary discharge is reported in m³/h. The head difference between
the two finest steps is 1.71 mm at the final saved time.

This is a standalone numerical reference. Integrating it with the OHQ app,
adding Richards-equation unsaturated storage and conductivity, and validating
rainfall/runoff partitioning over a sloping boundary are later modeling stages.

## Native OHQ implementation path

The pinned OpenHydroQual templates already include `Soil`, the horizontal
`soil_to_soil_H_link` with explicit face area and length, the vertical
`soil_to_soil_link`, surface-to-soil infiltration links, and
`soil_free_outflow`, whose flux is proportional to positive source pressure.
The upstream Drywell example uses the horizontal connector in a soil network.
Build the production section using native soil blocks and connectors. Use
this Python solver as an independent verification reference.

The native horizontal diffusion check exercises the stock connector with
`Kx/Kz = 2` and compares it with analytical small-amplitude decay:

```sh
python3 -m validation.diffusion --horizontal --output results/native-ohq-horizontal-diffusion.json
```

A native slope mesh must still match connector elevations, conductivities,
interface dimensions and outlet boundary placement. The closed horizontal
benchmark checks one connector direction. It does not verify those choices
for the full 2D rainfall and seepage-face case.
