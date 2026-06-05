#!/usr/bin/env python3
"""Run a project script with repository-root working directory and imports."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def module_dirs(repo_root: Path) -> list[str]:
    dirs = [str(repo_root)]
    for source in ("backend", "frontend"):
        source_root = repo_root / source
        if not source_root.exists():
            continue
        dirs.extend(str(path.parent) for path in source_root.rglob("*.py"))
    return sorted(set(dirs))


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python scripts/run_python.py <script.py> [args...]", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    target = (repo_root / sys.argv[1]).resolve()
    if not target.is_file():
        print(f"Python target not found: {sys.argv[1]}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    python_path = module_dirs(repo_root)
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    env["POLY_PROJECT_ROOT"] = str(repo_root)

    return subprocess.run(
        [sys.executable, str(target), *sys.argv[2:]],
        cwd=repo_root,
        env=env,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())

