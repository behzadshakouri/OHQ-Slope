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

The first native 2D grid uses two columns with eight soil cells each. It
runs through the OHQ console with stock horizontal links and the existing
cell-centred OHQ JSON vertical and surface links:

```sh
python3 -m validation.native_seepage_2d --output results/native-seepage-2d.json
```

Uniform rain reproduces the native stand-alone column to within 0.018 mm
of pressure head. With rain on the left only, the unwatered column gains
0.694 L over the run. Removing only the horizontal links gives zero gain.
The native cases use ponding and sealed sides and bases. They establish
redistribution in a small rectangular grid. Explicit sloping soil geometry still needs a native benchmark.

### Native atmospheric outlet

```sh
python3 -m validation.native_seepage_2d --outlet --output results/native-seepage-2d-outlet.json
```

The pressure-driven `soil_free_outflow` template discharges from eligible
faces on the lower right boundary. Each face has area equal to its cell
height times unit width, and a centre-to-boundary distance of half a cell
width. The stock link clips negative source pressure to zero. Existing
drainage collectors record the discharged water; these collectors do not
supply the outlet head. The benchmark checks native collector traces for
reverse flux and includes their storage in the water balance.

On the 4 × 16 grid the 7.5 s run discharged 0.355 L, and halving the step
from 15 to 7.5 s changed that volume by 0.22%. At 15 s, increasing resolution
from 2 × 8 to 4 × 16 changed it by 3.46%. The grid difference is measured
without a spatial convergence claim. The unwatered suction control produced
zero outlet discharge. The drainage case begins near saturation, so the
outlet discharges both initial soil water and rainfall-derived infiltration.

### Native rainfall partitioning and runon

```sh
python3 -m validation.native_seepage_2d --runoff --output results/native-seepage-2d-runoff.json
```

The stock `Catchment_link` routes ponded water from the first surface cell to
the second and then to a runoff collector. Native rainfall, soil infiltration,
and surface routing run together. The routing slope is prescribed as 0.01.
The underlying soil cells still form a rectangle.

Of the 1.1875 L applied to the first surface only, 0.7002 L left as runoff
and 0.4873 L remained as additional soil water at the end of the run. The
second surface received runon. A closed-surface control recorded zero runoff.
The maximum native balance residual was 1.5 × 10⁻¹³ m³.

### Native stepped-slope benchmark

```sh
python3 -m validation.native_seepage_2d --slope --output results/native-seepage-2d-slope.json
```

The synthetic section is 0.4 m wide with a sealed horizontal base. Four
terraces at elevations 0.30, 0.2625, 0.225 and 0.1875 m each span 0.10 m.
Horizontal soil links connect only cells with coincident elevation ranges.
Atmospheric outlets are enabled on the exposed step faces and the right toe.
The stock catchment links route runoff downslope using a prescribed grade
of 0.375. The upper half receives 70 mm/h for 3.75 minutes, followed by an
equal dry period. A specified near-saturated water content initializes the
soil; the outlets can therefore discharge initial water as well as recent
rainfall.

The coarse grid uses 26 cells over four columns at a 15-second maximum
step. The 104-cell grid subdivides each terrace horizontally and vertically
at the same maximum step, then repeats at 7.5 seconds. Terrace elevations
and extents are identical across the two resolutions. Pressure histories
are compared at fixed lower-face and toe coordinates. The comparisons
measure grid and time-step sensitivity for this stepped geometry.

The finest run partitions 0.875 L of rainfall into 0.530 L of runoff, 0.260 L
of seepage discharge and 0.085 L of soil storage gain, with zero final surface
storage. The maximum balance residual across the three runs is 2.1 × 10⁻¹¹
m³. Grid refinement changes peak saved probe pressure by up to 5.53 mm;
halving the maximum step changes it by up to 1.47 mm. These synthetic results
verify coupling across the native components. Transfer to the GeoStudio slope
requires matching its geometry, materials, initial pressures and boundaries.

### Comparison with an audited GeoStudio flume archive

The external flume case runner takes the saved archive and the two audited
input mappings. It verifies the archive SHA-256, finds the Transient Seepage
material region, reads the original initial pressures, and compares four
actual archive mesh-node locations at saved times.

```sh
python3 -m validation.geostudio_native_case /path/to/project.gsz /path/to/case_input_manifest.json /path/to/archived_boundary_evidence.json --columns 8 --layers 14 --output results/flume-2h-coarse.json
python3 -m validation.geostudio_native_case /path/to/project.gsz /path/to/case_input_manifest.json /path/to/archived_boundary_evidence.json --columns 16 --layers 28 --output results/flume-2h-fine.json
```

The two-hour case uses a midpoint staircase, fitted OHQ hydraulic functions,
rainfall over horizontal plan area and sealed back and base. The surface
maps the reviewed rainfall condition to the existing reviewed-infiltration
OHQ JSON components, including an area-specific excess-water collector.
Stock one-way outlets serve exposed risers and the right exit. This replaces
the smooth sloping face with distinct tread and riser conditions. The mapped
geometry, hydraulic fit and boundary form are approximations to the
archived formulation. The diagnostic budget uses a unit out-of-plane width.
