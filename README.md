# OHQ-Slope

Rainfall-driven slope hydrology, factor of safety, and uncertainty quantification using OpenHydroQual.

This repository is the software workspace. Manuscripts, reference papers, GeoStudio archives, and publication figures remain outside it. The initial commit provides the project structure and a pinned engine dependency; slope physics and ensemble workflows are not implemented yet.

## Setup

```sh
git clone --recurse-submodules <repository-url>
cd OHQ-Slope
python3 scripts/check_dependency.py
```

For an existing clone, run `git submodule update --init --recursive`. Build OHQ using the instructions inside `external/OpenHydroQual/OHQLib/BUILD.md` or its headless runner documentation. No prebuilt engine is included.

## Structure

- `components/`: verified custom OHQ JSON diagnostics.
- `models/`: small runnable model definitions and permitted synthetic inputs.
- `stability/`: reference FS calculations, initially external to OHQ.
- `uncertainty/`: sampling and ensemble execution.
- `validation/`: analytical benchmarks and comparison code.
- `config/`: dependency provenance and future run specifications.
- `external/OpenHydroQual/`: pinned engine submodule.
- `results/`: ignored generated outputs.

## Development sequence

1. Verify the engine setup and a small hydrologic case.
2. Verify an external FS calculation against hand calculations.
3. Implement pressure mapping and compare compatible reference cases.
4. Propagate defensible parameter uncertainty.
5. Integrate a JSON diagnostic and verify agreement with the reference calculation.
6. Optimize ensemble execution if necessary.
7. Add rainfall-conditioned pseudostatic seismic loading.

See [development notes](docs/development.md). The OHQ pin identifies a starting source version, not a validated slope-model release. No uncommitted changes from the existing OHQ checkout are included.

## Dependencies and licensing

OpenHydroQual retains its upstream license in `external/OpenHydroQual/LICENSE`. No separate license for newly authored project code is selected yet.
