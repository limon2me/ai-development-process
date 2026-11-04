#!/usr/bin/env python3
"""Helper utility to freeze, verify, or unfreeze accepted tests for product-development."""
from __future__ import annotations

import hashlib
import pathlib
import sys


def compute_snapshot(tests_dir: pathlib.Path, repo_root: pathlib.Path) -> str:
    lines: list[str] = []
    for p in sorted(tests_dir.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts and not p.name.startswith("."):
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            rel = p.relative_to(repo_root).as_posix()
            lines.append(f"{digest}  {rel}")
    return "\n".join(lines) + "\n"


def get_default_tests_dir(repo_root: pathlib.Path) -> pathlib.Path:
    for name in ("tests", "test"):
        candidate = repo_root / name
        if candidate.is_dir():
            return candidate
    return repo_root / "tests"


def get_default_state_file(repo_root: pathlib.Path) -> pathlib.Path:
    # Prefer .git if present (always gitignored), else .gemini or .agents
    git_dir = repo_root / ".git"
    if git_dir.is_dir():
        return git_dir / "frozen_tests.sha256"
    gemini_dir = repo_root / ".gemini"
    if gemini_dir.is_dir():
        return gemini_dir / "frozen_tests.sha256"
    return repo_root / ".agents" / "state" / "frozen_tests.sha256"


def main() -> int:
    repo_root = pathlib.Path.cwd().resolve()
    tests_dir = get_default_tests_dir(repo_root)
    state_file = get_default_state_file(repo_root)

    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "freeze":
        if not tests_dir.is_dir():
            print(f"Error: tests directory not found at {tests_dir}")
            return 1
        state_file.parent.mkdir(parents=True, exist_ok=True)
        snap = compute_snapshot(tests_dir, repo_root)
        state_file.write_text(snap, encoding="utf-8")
        print(f"Frozen {len(snap.splitlines())} test files in {state_file}")
        return 0
    if action == "verify":
        if not state_file.is_file():
            print(f"No frozen snapshot found ({state_file} missing).")
            return 1
        expected = state_file.read_text(encoding="utf-8")
        actual = compute_snapshot(tests_dir, repo_root)
        if expected == actual:
            print(f"OK: all {len(actual.splitlines())} test files match frozen snapshot.")
            return 0
        print("MISMATCH: test files differ from frozen snapshot!")
        return 2
    if action == "unfreeze":
        if state_file.is_file():
            state_file.unlink()
            print(f"Unfrozen tests (removed {state_file}).")
        else:
            print("Tests were not frozen.")
        return 0

    print("Usage: freeze_tests.py [freeze|verify|unfreeze]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
