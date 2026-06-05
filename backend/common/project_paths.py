#!/usr/bin/env python3
"""Shared project path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    """Return the repository root used for runtime data files."""

    env_root = os.environ.get("POLY_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()

    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists() or (parent / ".env.example").exists():
            return parent

    return Path.cwd().resolve()

