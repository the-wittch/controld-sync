# Contributing

Thank you for contributing to Control D JSON Synchronizer.

## Development setup

The runtime uses Python's standard library. Use Python 3.11 or newer. For
development, install the package and its quality tools in an isolated
environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

Run the validation suite before opening a pull request:

```sh
python3 -m unittest discover -s tests -v
python3 -m py_compile src/controld_sync/*.py scripts/*.py
python3 scripts/validate_config.py config.toml
ruff check .
ruff format --check .
pyright
```

## Pull requests

- Keep changes focused and explain behavior changes.
- Add regression tests for synchronization or parsing changes.
- Do not commit API tokens, local configuration files, cache files, or
  credentials.
- Keep automated source URLs pinned to immutable commit SHAs.
- Update [`CHANGELOG.md`](CHANGELOG.md) for user-visible changes.
- Use the pull request template fields and ensure CI passes.

Changes to workflows, configuration, security behavior, or synchronization
semantics require review by the repository owner.

## Reporting security issues

Do not disclose vulnerabilities or credentials in a public issue. Follow the
private reporting instructions in [`SECURITY.md`](SECURITY.md).
