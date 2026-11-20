# Controlled diagnosis of the transient pressure difference

This study isolates three differences between the production OHQ column and the
independent ponding reference. It does not change the production app or OHQ's
pinned source. The synthetic case is the 0.5 m sealed column described in
[verification.md](verification.md): 40 mm/h for three hours, six-hour duration,
and a 0.25 m pressure-monitoring depth.

## Design

All eight combinations run through the same conservative independent solver with
32 cells, a maximum 0.000125-day step, and identical initial conditions, forcing,
constitutive storage, and output times. The factors are:

| Factor | Production law | Alternative |
|---|---|---|
| Head reference | Block top | Cell centre |
| Interior conductivity | Maximum adjacent K, equivalent to maximum Se for this homogeneous soil | Arithmetic mean K |
| Surface boundary | Depth smoothing h/(h+0.001) | Water-availability/ponded-head complementarity |

The alternative boundary uses the selected head location in its gradient. The
surface-to-first-head length remains dx/2 in every variant, matching the
production connector; the inconsistent top-reference distance is therefore part
of the geometry factor. These controls describe this homogeneous, sealed case;
they do not establish equivalent rules for heterogeneous materials or drainage.

## Conditional effects

The largest production-law minus alternative-law pressure difference occurs at
0.75 h and is approximately -0.04683 m. Changing one factor while holding the
other two at their production values gives:

| Single change | Signed pressure change at 0.75 h (m) | Maximum remaining difference from the all-alternative 32-cell run (m) |
|---|---:|---:|
| Move heads to cell centres | +0.05260 | 0.01824 |
| Use arithmetic interior K | -0.04803 | 0.10561 |
| Replace surface smoothing | +0.02927 | 0.02661 |

Head placement and the surface boundary both contribute materially. The
maximum-K rule partly offsets those effects in this example: replacing it alone
makes agreement worse. Effects are conditional and interact, so these numbers
must not be added or interpreted as independent percentages of the original
error. A coordinate shift is not established as a general correction by one case.

## Separating implementation error from equation differences

The independent solver's production-law combination uses the same top-reference,
maximum-K, and smoothed-surface equations as OHQ. Actual pinned OHQ runs approach
that matched-law calculation as the OHQ time step decreases:

| OHQ maximum step (h) | Maximum pressure difference from matched independent solver (m) |
|---|---:|
| 0.016667 | 0.01097 |
| 0.008333 | 0.00434 |
| 0.004167 | 0.000978 |

Meanwhile, OHQ's pressure difference from the all-alternative 32-cell run remains
about 0.047 m. Smaller time steps therefore improve agreement on the **same
discrete equations**, but do not remove the boundary/geometry/conductivity gap.
All OHQ water-balance residuals in this comparison are below 3e-11 m³.

## Spatial refinement and its limits

Running the production-law and all-alternative formulations at the same grid
and time step gives maximum pressure differences of:

| Cells in both formulations | Difference (m) |
|---|---:|
| 32 | 0.04683 |
| 64 | 0.02814 |
| 128 | 0.01683 |

These 64/128-cell runs use the independent solver only; the legacy formulation still
allows at most 32 OHQ cells. The gap decreases, but 128 cells still leave roughly
1.7 cm between formulations. The independent all-alternative reference's
32-to-64 and 64-to-128 differences are 0.00659 and 0.00345 m. Halving its 128-cell
time step changes pressure by 0.00122 m. These are empirical differences, not
rigorous error bounds or evidence of complete transient convergence.

An explicitly selectable [cell-centred column formulation](cell_centred_column.md)
now implements the alternative connectors as project JSON components and has been
checked across forcing, drainage, and moisture regimes. It supports up to 64 OHQ
cells; existing requests retain the legacy formulation for comparison.
Do not silently replace one conductivity rule in existing jobs or proceed to
experimental failure-time inference on the strength of this single benchmark.

## Reproduce

```sh
python3 -m validation.ponding_ablation --output results/ponding-ablation.json
```

The output includes all eight variant summaries, conditional effects at the
common peak time, actual OHQ time refinement, independent grid/time refinement,
water balances, and source/engine hashes. Raw OHQ scripts, outputs, and logs stay
in its `_files` directory. Regression tests check the matched-law agreement and
the analytical top-reference hydrostatic offset. The original independent
reference remains the default; production model equations are unchanged.
