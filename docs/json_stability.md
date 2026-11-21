# OHQ JSON stability diagnostic

`components/infinite_slope.json` defines a separate **Infinite Slope Diagnostic** block loaded through OHQ's `addtemplate`. It does not copy Soil or modify the pinned OHQ dependency. The calculation is read-only: mapped pressure and mechanical inputs enter the block, and FS/stress quantities are observed. There is no feedback to water flow.

The block accepts cohesion (kPa), friction angle (degrees), total unit weight (kN/m³), slope angle (degrees), vertical failure depth (m), and pressure head (m). It computes the same uniform infinite-slope balance described in [calculation.md](calculation.md), with water unit weight 9.81 kN/m³, negative-head suction strength omitted, and no seismic or ponded-water mechanical surcharge. Its inert zero-flow Storage quantity only anchors the engine's balance solver; it is not physical soil storage.

## Interpreter compatibility

The pinned general expression interpreter does not implement sine, cosine, or tangent. Calling an unsupported function would silently return its argument, so this template does not use such calls. It evaluates sine and cosine using explicit Taylor polynomials through powers 19 and 20, respectively, after converting degrees to radians. Friction tangent is their ratio. This representation is verified over the app's angle range: 0.1–89° slope and 0.01–89° friction. Accuracy outside the supported range is not established. No kernel implementation is enabled.

## App and uncertainty integration

Choose **OHQ JSON component** under **Stability calculation**, or add `"stability_engine": "ohq_json"` to a CLI/API scenario. The browser selects OHQ JSON when the console is available and Python reference otherwise. API/CLI scenarios that omit `stability_engine` retain the original `python_reference` default for reproducibility. The Python reference also supports prescribed pressures without an OHQ build.

The external orchestrator samples the same seeded parameters as before. For each realization it sends the selected pressure-history states to a generated diagnostic model, runs OHQ, and uses the resulting JSON-component FS values in the summaries. This supports deterministic, mechanical-only, and paired hydraulic/mechanical runs. Each realization is independently checked against the Python reference before aggregation. Limits are 100 realizations and 10,000 sample-time evaluations per JSON-engine job; each history has at most 500 rows.

The pressure-to-failure-plane mapping remains in the external adapter. This is explicit postprocessing through OHQ's interpreter, not an assertion that a diagnostic can read arbitrary quantities from other blocks. Generated inputs and observations stay under each job's `stability/` directory. The final native observation is used; time-zero observation placeholders are not treated as calculated FS.

The adapter validates the physical domain before launching. It also checks the JSON `contact_valid` flag and requires agreement with Python within relative or absolute tolerance 1e-10. Invalid contact, engine failure, cancellation, or parity mismatch fails the job rather than dropping a sample or reporting a partial probability. When using the template manually, enforce positive depth/weight, angles strictly between 0 and 90°, nonnegative cohesion, and nonnegative effective normal stress; a raw expression value alone is not a valid FS when these conditions fail.

Results identify `stability_engine`, record the template/binary hashes and maximum FS difference, and count checked realizations. Server provenance includes both template and adapter hashes. Regression checks cover an independent dry force balance, pressure effects, angle limits, seeded mechanical ensembles, paired hydraulic states, cancellation, domain rejection, and rejection of mismatched results.

## Verification limits and remaining stages

JSON/Python agreement verifies the mechanical implementation, not the hydrologic accuracy or the experimental case. [Ponding verification](verification.md) currently finds a remaining transient pressure difference of about 0.044 m at 32 cells in its synthetic comparison. That discrepancy must be resolved before interpreting experimental failure timing. Site-informed distributions, correlations, independent external stability comparisons, and any interpreter/kernel parity remain separate work.
