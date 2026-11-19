# Development notes

Keep hydrology, stability, and ensemble orchestration behind small interfaces. Start with interpreted OHQ runs using Python bindings or the headless runner. Do not duplicate the complete Soil template as the initial extension strategy.

The external stability calculation will consume time, pressure at specified failure surfaces, geometry, and mechanical parameters. Define units, pressure sign, angle convention, and failure geometry explicitly before implementation. Do not equate block thickness with failure depth or assume representative block pressure is bottom pressure.

Verify water balance, initial conditions, independent ensemble initialization, numerical run status, and sampling resolution. Record input and template hashes, seed, distributions, engine commit, build settings, and solver settings for each ensemble. Treat numerical failures separately from physical instability.

Only use generated kernels after comparison with the interpreter. Regenerate them when models or templates change. Check that parameter updates affect intended quantities and initial states.

Engine fixes belong in an OHQ branch with appropriate validation. Update this project's submodule pin deliberately. Changes from the original working checkout are not included in this dependency baseline.

External reference datasets should be described by a local configuration or manifest with checksums and provenance. Do not copy paper assets into this repository. A reproducible small synthetic benchmark belongs here.

The seismic extension will initially use a pseudostatic coefficient and rainfall-conditioned pressures. Dynamic deformation, liquefaction, and shaking-generated pore pressure require separately scoped mechanics.
