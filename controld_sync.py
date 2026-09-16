#!/usr/bin/env python3
"""Compatibility wrapper for the :mod:`controld_sync` package."""

from controld_sync import *  # noqa: F401,F403 - preserve the legacy API
from controld_sync.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
