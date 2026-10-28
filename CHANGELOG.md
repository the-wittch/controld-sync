# Changelog

All notable changes to this project are documented here.

## [1.2.0] - 2026-10-28

### Fixed

- Dependabot auto-merge waits for CI, enables GitHub auto-merge without failing
  its own check (a red `merge` check was blocking PRs), and groups Actions
  updates so CodeQL `init`/`analyze` stay on the same version.
- Dependabot auto-merge reads the update type from `dependabot/fetch-metadata`
  instead of the PR title, so grouped updates are no longer always refused.
- `www.` prefixes are no longer stripped. `www.googletagmanager.com` in an allow
  folder was being uploaded as `googletagmanager.com`, allowing the whole domain.
  The first apply after upgrading replaces the affected folders.
- The HaGeZi pin updater fails instead of passing with a warning when it can't
  open its PR, and starts CI on the PR it opens.
- A failed restore after an atomic replace is reported instead of swallowed.
- Dry runs no longer write the cache when a folder fails.
- Scheduled sync failures comment on the open failure issue instead of opening
  a new one each time.

### Security

- Source URLs must use HTTPS and are capped at 16 MiB.
- The Control D client refuses redirects so the bearer token can't be forwarded.
- `CONTROLD_API_TOKEN` is only exposed to the sync step, not to `pip install`.
- Workflow checkouts no longer persist the `GITHUB_TOKEN` where it isn't needed.

### Changed

- CI and CodeQL run on pushes to `main` and on pull requests instead of every
  branch push. Config validation runs once per CI run; the separate
  `config-validation.yml` workflow was removed.

## [1.1.3] - 2026-10-13

### Fixed

- Atomic folder replace no longer tries to copy rules into a second group while
  they still exist in the original. Control D custom rules are unique per
  profile, so replace now snapshots in memory, deletes the folder, recreates it,
  and restores from the snapshot on failure.
- Multi-label Control D wildcards such as `*.edu.eu` and `*.co.com` are
  preserved instead of being collapsed to the bare domain.
- Mapped folders that share rule hostnames are rejected before any writes.

### Changed

- Baseline config maps `Spam TLDs` instead of also mapping
  `Most Abused TLDs` (`spam-tlds-combined`), which fully contains `Spam TLDs`.
- `scripts/validate_config.py` downloads mapped sources and fails on overlapping
  rule hostnames, so CI catches conflicts before the weekly sync.
- `--generate-hagezi-config` keeps overlapping folders in `[folders]` but only
  maps a conflict-free subset to the init profile.

## [1.1.2] - 2026-09-20

### Fixed

- Install the packaged CLI before scheduled GitHub Actions synchronization.

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
