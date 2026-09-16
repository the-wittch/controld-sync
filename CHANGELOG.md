# Changelog

All notable changes to this project are documented here.

## [1.1.0] - 2026-09-15

### Added

- Installable `controld-sync` Python package with a standard `src/` layout.
- `controld-sync` console command for installed environments.
- Ruff formatting and linting checks.
- Pyright static type checking.
- CI coverage for Python 3.11 through 3.14.
- Pull request validation guidance and a pull request template.

### Changed

- Replaced the legacy root-level script entry point with the packaged CLI.
- Updated documentation, workflows, and repository links for `controld-sync`.

## [1.0.0] - 2026-09-15

### Added

- Configuration-driven synchronization of arbitrary JSON domain sources.
- HaGeZi Control D folder discovery and immutable source pinning.
- Control D allow/block action preservation.
- Dry-run, validation, drift detection, caching, retries, and rollback attempts.
- Profile listing and structured synchronization summaries.
- Weekly GitHub Actions synchronization.
- CI, CodeQL, Dependabot, configuration validation, and scheduled HaGeZi
  update checks.
- MIT license, security policy, contributor guidance, and issue templates.
