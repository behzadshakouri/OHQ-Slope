# Reviewed infiltration surface boundary (offline hydrology only)

Select `"surface_boundary": "reviewed_infiltration"` in an external cell-centred
column study. Omission, or `"closed_ponding"`, retains the existing surface store.
This is an optional JSON component, not an engine patch. The browser does not
expose it; the FS workflow rejects it until its hydrologic representation is
assessed. App resource/input bounds and the pinned engine remain unchanged.

## Equations and accounting

Let R ≥ 0 be rainfall volume per day, A the unit horizontal area, dz the first
cell thickness, and psi its pressure head. With constant saturated conductivity
Ks at the half-cell surface interface, the Darcy capacity at zero boundary
pressure is

```
Q0 = A Ks (dz/2 - psi) / (dz/2)
Qnet = min(R, Q0)                  positive into the soil
Qexcess = R - Qnet = max(0, R-Q0)
```

When Q0 ≥ R, rainfall limits infiltration and the implied boundary head is
`psi_b = psi - dz/2 + R dz/(2 A Ks) ≤ 0`. Otherwise psi_b = 0 and excess water
leaves. Negative Q0 permits soil exfiltration, including in dry intervals.
There is no indefinite external water supply at zero head. This is a zero-head
cap with atmospheric rain supply, not a prescribed zero-head source at all times.
It does not add evaporation or surface suction limits.

The JSON expresses this without remote link dependencies: a rain link passes R
from the catchment ledger to the first soil cell, and a second link transfers
Qexcess from that cell to a cumulative collector. Thus the soil's **net** input
is Qnet. The native link named `Infiltration` is gross R for this option and must
not be interpreted as net infiltration. Both links disable automatic outflow
scaling because the constitutive allocation enforces the supply condition;
post-run conservation and nondecreasing discharge are checked explicitly.

The collector's precipitation source is read to calculate R; it is **not**
listed as a balance inflow and does not add rain a second time. The catchment
has equal rain input and output and remains a zero-storage bookkeeping object.
The template assumes the adapter's 1 m² area; it is not a general variable-area
catchment runoff model. No empirical overflow coefficient or relaxation time
is introduced.

Every native saved time is checked against

```
initial soil water + cumulative rainfall
  = current soil water + surface water + basal discharge + surface excess
```

`surface_excess_m3` includes rejected rain **and** exfiltration; its cumulative
value cannot distinguish the two. `cumulative_net_infiltration_m3` is cumulative
rain minus this ledger and may decrease during exfiltration. Surface storage
must remain zero to within 1e-10 m³, and surface excess must not decrease beyond
1e-10 m³ per native increment. Floating-point traces within that tolerance are
retained rather than clipped. Existing global conservation rejection remains
1e-4 m³, with actual residuals reported for each case.

## Verification and limits

`python3 -m unittest discover -s tests -p test_reviewed_surface.py` checks:

- explicit selection and rejection of unsupported formulations/FS coupling;
- high rainfall against an independently integrated finite-volume boundary;
- the analytical sealed hydrostatic limit with psi equal to depth and zero
  surface head, including cumulative discharge calculated from the storage law;
- rain-limited infiltration and no rain, with no artificial water source;
- exfiltration from a valid near-saturated initial state without rain.

The independent solver's reviewed option removes its ponding state equation,
integrates Qnet directly and accumulates R-Qnet. It shares the documented
constitutive assumptions, not the native two-link implementation.

This controls one boundary assumption. It is consistent with the conceptual
zero-pressure review described in [Seequent's SEEP/W tutorial](https://files.seequent.com/GeoStudio/SeepW/SEEPW%20Tutorial.pdf).
It does not reproduce GeoStudio's finite-element boundary review algorithm,
node flux partitioning, constitutive splines, surface geometry or lateral flow.
A numerical comparison with archived results remains model-to-model evidence;
original observations and spatial convergence still need assessment.

The reviewed option uses native `nr_tolerance=1e-12`,
`nr_block_tolerance=1e-10` and `update_jacobian_every_iteration=Yes`. The other
surface option retains its existing settings. Tightening only the global Newton
tolerance did not remove a roughly 2e-10 m³ per-step decrease in a cumulative
collector in an initial sensitivity run: the engine also has stagnation tests
and reuses its Jacobian by default. Those failed diagnostics are retained;
validation was not relaxed or the trace clipped to make the run pass. Refreshing
the Jacobian and checking local balance explicitly address this behavior.
