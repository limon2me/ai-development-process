#!/usr/bin/env python3
"""Injects critical project rules from CLAUDE.md / AGENTS.md / GEMINI.md at SessionStart."""
from __future__ import annotations

import json
import pathlib
import re
import sys


def get_repo_root(data: dict) -> pathlib.Path:
    workspace_paths = data.get("workspacePaths") or []
    if workspace_paths and workspace_paths[0]:
        return pathlib.Path(workspace_paths[0]).resolve()
    return pathlib.Path.cwd().resolve()


def find_rules_file(repo_root: pathlib.Path) -> pathlib.Path | None:
    for name in ("CLAUDE.md", "AGENTS.md", "GEMINI.md"):
        candidate = repo_root / name
        if candidate.is_file():
            return candidate
    return None


def extract_sections(text: str, heading_patterns: list[str]) -> str:
    extracted: list[str] = []
    # Check for explicit injection markers first
    marker_match = re.search(
        r"<!--\s*inject-hard-limits\s*-->(.*?)<!--\s*/inject-hard-limits\s*-->",
        text,
        re.DOTALL,
    )
    if marker_match:
        return marker_match.group(1).strip()

    # Extract matching heading sections (## or ###)
    for pattern in heading_patterns:
        regex = re.compile(
            rf"(^#{{2,3}}\s+{pattern}\b.*?)(?=^#{{2,3}}\s+|\Z)",
            re.MULTILINE | re.DOTALL | re.IGNORECASE,
        )
        match = regex.search(text)
        if match:
            extracted.append(match.group(1).strip())
    return "\n\n".join(extracted)


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        repo_root = get_repo_root(data)
        rules_file = find_rules_file(repo_root)
        if not rules_file:
            print(json.dumps({}))
            return

        text = rules_file.read_text(encoding="utf-8")
        patterns = [
            r"(?:жёсткие\s+)?ограничения.*",
            r"две\s+сессии.*",
            r"прогон\s+тестов.*",
            r"коммиты(?:\s+и\s+релиз)?.*",
            r"hard\s+limits?.*",
            r"restrictions?.*",
            r"security.*",
            r"testing.*",
        ]
        sections = extract_sections(text, patterns)
        if not sections:
            print(json.dumps({}))
            return

        message = (
            f"Автоматическая выдержка обязательных правил из {rules_file.name} "
            f"(полный текст {rules_file.name} всё равно обязательно прочитай до конца файла):\n\n"
            + sections
        )
        output = {
            "injectSteps": [
                {
                    "systemMessage": {
                        "systemMessage": message,
                    }
                }
            ]
        }
        print(json.dumps(output, ensure_ascii=False))
    except Exception:
        print(json.dumps({}))


if __name__ == "__main__":
    main()
