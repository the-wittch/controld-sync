# Control D JSON sync

[![Sync Control D folders](https://github.com/the-wittch/controld_sync/actions/workflows/controld-sync.yml/badge.svg)](https://github.com/the-wittch/controld_sync/actions/workflows/controld-sync.yml)

This small, dependency-free CLI synchronizes JSON folder data into matching
custom-rule folders on one or more Control D profiles. It is configured with
TOML, modeled after the reference `controld-hagezi-sync` project, and supports the
Control D/HaGeZi export shape (`group.group` plus `rules[].PK`) and generic
JSON containing domain fields. A directory can contain many folders; each file
is synchronized independently. It is suitable for periodically pulling lists
and running from cron or a system timer.

## Setup

Copy [`config.toml.example`](config.toml.example) to `config.toml` and edit the
profile names, folder sources, and profile-to-folder mappings:

```sh
cp config.toml.example config.toml
```

Create a Control D API token with permission to manage profiles, then export it
without putting it in a config file:

```sh
export CONTROLD_API_TOKEN='your-token'
```

The API uses `https://api.controld.com` by default. Set
`CONTROLD_API_BASE_URL` only when using a test proxy.

## Configuration

The configuration has four sections:

- `[settings]`: `api_token`, `dry_run`, `cache_file`, `atomic_replace`, and
  `fail_on_drift`.
- `[profiles]`: exact Control D profile names.
- `[folders]`: folder name to HTTPS JSON URL, local JSON file, or local directory.
- `[profile_folders]`: which configured folders each profile receives.

The `CONTROLD_API_TOKEN` environment variable overrides `settings.api_token`,
which is useful for GitHub Actions. `dry_run = true` is the safe default; use
`--apply` for a write run.

Apply runs persist a SHA-256 hash of each normalized source in `cache_file`
(default `.controld-sync-cache.json`), keyed by profile and folder with an
update timestamp. The cache is written atomically and is never written by a
normal dry run. The hash is informational: remote folders are still checked
on every run, so out-of-band changes are detected. Use `--check-drift` or
`fail_on_drift = true` to make drift a hard failure. `--no-cache` disables
cache access; `--validate` checks remote folders without writing; and
`--check-updates` fetches every configured upstream source, compares its
normalized SHA-256 hash with the last successful apply, and reports
`source_changed` in the JSON summary. It is source-only (it does not query or
modify Control D groups) and never advances or writes the cache. Successful
runs also print structured JSON folder summaries suitable for GitHub Actions.

The token is sent only as an HTTPS `Authorization: Bearer` header to the
configured Control D API base URL. JSON source URLs are fetched without the
Control D token. Do not put a real token in `config.toml`, because repository
files, pull requests, and checkout artifacts are not secret storage. Use the
`CONTROLD_API_TOKEN` GitHub secret instead.

For automated `--apply` runs, pin GitHub-hosted source URLs to immutable commit
SHA values rather than `main` or another moving branch. The example
configuration uses reviewed commit pins. The HaGeZi generator resolves a
branch or tag once and writes the resulting commit SHA into the generated
configuration. Review and regenerate the file deliberately when updating
upstream sources.

## Usage

Generate a token-free configuration containing every HaGeZi Control D folder
and assign them to a Control D profile named `Init`:

```sh
python3 controld_sync.py --generate-hagezi-config config.hagezi.toml
```

The command discovers the current `*-folder.json` files from HaGeZi's GitHub
repository, reads each folder's `group.group` name, and writes source URLs
pinned to the resolved Git commit plus the `[profile_folders]` mapping. It does
not require a Control D token. Use `--init-profile-name NAME` to choose a
different profile name. Review the generated file before applying it; new
HaGeZi folders may be added upstream over time, so regenerate it when you want
to refresh the list.

List the profiles available to the token:

```sh
CONTROLD_API_TOKEN='your-token' \
  python3 controld_sync.py --config config.local.toml --list-profiles
```

The output contains each profile name followed by its Control D ID:

```text
Kids    abc123
Adults  def456
```

Dry-run is the default:

```sh
python3 controld_sync.py --config config.toml
```

Apply the changes:

```sh
python3 controld_sync.py --config config.toml --apply
```

Validate without changing Control D:

```sh
python3 controld_sync.py --config config.toml --validate
```

The synchronizer only removes rules in mapped folders, so other custom rules
are untouched. It refuses to write when a source contains no valid domains.
Control D folder exports retain each rule's `action.do` and `action.status`
values, so HaGeZi allow folders are imported as allow rules rather than being
treated as block rules. Generic JSON sources without action metadata default to
`do = 0`, `status = 1`.
When a mapped folder changes, apply mode builds a replacement group, validates
the imported rule set, and retains the previous set in a `<folder>_OLD` backup. Backup names are shortened safely to Control D's
32-character limit. GET requests retry transient failures with
`Retry-After`/exponential backoff; write requests are never replayed
automatically.
If validation or a later API request fails, it attempts to remove the partial
replacement and restore the original group. Set `atomic_replace = false` to
use the legacy add/remove update strategy.

The Control D/HaGeZi folder format works directly:

```json
{"group": {"group": "Badware Hoster"}, "rules": [{"PK": "ads.example"}]}
```

Control D exports are validated strictly: `group.group` must be a non-empty
string, `rules` must be an array, and every rule must contain a valid `PK`.
Generic JSON lists and nested domain objects remain supported.

Control D selector rules such as `@RU`, `@CN`, and `@NG` are also supported.
For GitHub-hosted JSON, use an immutable `raw.githubusercontent.com` URL rather
than the normal GitHub `/blob/` page URL. For example:

```toml
"Potentially Malicious IPs" = "https://raw.githubusercontent.com/yokoffing/Control-D-Config/main/folders/potentially-malicious-ips.json"
```

Generic JSON may be a list of domain strings, nested objects containing
`domain`, `hostname`, `host`, `PK`, `domains`, `hosts`, `entries`, or `rules`,
or a combination:

```json
["ads.example", "tracker.example"]
```

The script batches additions in groups of 500 and normalizes case, trailing
dots, `*.example` and `||example^` entries.

## HaGeZi example

Download one or more JSON folders into a directory and sync them:

```sh
mkdir -p lists
curl -fsSL 'https://raw.githubusercontent.com/hagezi/dns-blocklists/main/controld/badware-hoster-folder.json' \
  -o lists/hagezi.json
CONTROLD_API_TOKEN='your-token' \
  python3 controld_sync.py lists --profile PROFILE_ID --apply
```

The folder name comes from `group.group`; if absent, the filename stem is used.
Check the source format before using it; plain hosts or Adblock files should be
converted to JSON first.

## Weekly GitHub Action

The repository includes [the weekly workflow](.github/workflows/controld-sync.yml).
It runs every Sunday at 03:00 UTC and can also be started manually from the
Actions tab.

Configure these repository settings before enabling it:

- Add a repository **secret** named `CONTROLD_API_TOKEN`.
- Commit `config.toml` after removing `settings.api_token`, or keep it private
  and configure the workflow accordingly.
- Put local JSON files referenced by the config in the repository.

The workflow uses `--apply`, so it updates Control D folders on every run.
The API token is passed through the environment and is not written to logs.

## Dependabot

Dependabot checks the pinned GitHub Actions used by the workflow and opens
reviewable pull requests when updates are available. It runs weekly and does
not update the pinned HaGeZi source commits; regenerate `config.toml` manually
when you intentionally want to update those sources.
