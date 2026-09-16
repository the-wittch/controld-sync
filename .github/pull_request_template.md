## Summary

<!-- What changed and why? -->

## Validation

- [ ] `python -m unittest discover -s tests -v`
- [ ] `python -m py_compile src/controld_sync/*.py scripts/*.py`
- [ ] `python scripts/validate_config.py config.toml`
- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pyright`

## Security and configuration impact

<!-- Note any token, workflow, source URL, permission, or configuration changes. -->

## Documentation

- [ ] README, changelog, or other documentation updated when needed.
