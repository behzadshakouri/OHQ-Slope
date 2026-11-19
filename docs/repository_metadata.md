# Repository presentation and GitHub settings

The presentation follows the useful conventions in the author's GIStoOHQ and
OpenWatershedTwin repositories: a concrete About description, linked OHQ
resources, discoverable scientific topics, software citation metadata, license
information, and automated checks. OHQ-Slope is described as a local research
prototype; digital-twin, earthquake, field-validation, and release-version claims
are not included in its metadata.

## About and topics

The authoritative values are in [`.github/repository.json`](../.github/repository.json).
The website links to OpenHydroQual, following GIStoOHQ. The description is:

> Rainfall-driven slope stability and uncertainty quantification with OpenHydroQual, verified infinite-slope mechanics, and a local scenario app.

GitHub About and topic tags are repository settings. Committing or pushing these
files does **not** apply those settings. Preview them locally with:

```sh
python3 scripts/configure_repository.py
```

Apply them from an authenticated environment with:

```sh
python3 scripts/configure_repository.py --apply
```

The helper uses `GH_TOKEN` or `GITHUB_TOKEN`, checks that the authenticated user
is `behzadshakouri`, and updates only the description, website, and full topic
list of `behzadshakouri/OHQ-Slope`. It does not push code. The GitHub token needs
repository Administration write permission. Do not save tokens in tracked files.
Alternatively, copy these values into the repository's About settings on GitHub.

## Checks and citation

The Checks workflow runs reference/guard/API tests, the pinned source check,
metadata preview, and JavaScript syntax checking on Python 3.10 and 3.13. Native
OHQ integration tests skip unless its console is built; a passing badge does not
certify hydrologic validation. The workflow activates after it is pushed.

`CITATION.cff` enables software citation metadata and requests the exact commit.
No release date, version, or DOI is invented before an actual release exists.
The selected project license is AGPL-3.0-or-later; third-party licenses and
copyright notices remain separate in `NOTICE.md` and the dependency checkouts.
