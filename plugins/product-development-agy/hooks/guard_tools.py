#!/usr/bin/env python3
"""PreToolUse safety and process guard for product-development in Antigravity."""
from __future__ import annotations

import json
import pathlib
import re
import sys


def respond(decision: str, reason: str = "") -> None:
    payload: dict[str, str] = {"decision": decision}
    if reason:
        payload["reason"] = reason
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def get_repo_root(data: dict) -> pathlib.Path:
    workspace_paths = data.get("workspacePaths") or []
    if workspace_paths and workspace_paths[0]:
        return pathlib.Path(workspace_paths[0]).resolve()
    return pathlib.Path.cwd().resolve()


def is_env_secret_path(path_str: str) -> bool:
    if not path_str:
        return False
    name = pathlib.Path(path_str).name
    if name in (".env.example", ".env.sample", ".env.template", ".env.schema"):
        return False
    return (
        name == ".env"
        or (name.startswith(".env.") and not name.endswith((".example", ".sample", ".template", ".schema")))
        or name.endswith(".env")
    )


def is_test_path(path_str: str, repo_root: pathlib.Path) -> bool:
    if not path_str:
        return False
    try:
        p = pathlib.Path(path_str)
        if not p.is_absolute():
            p = (repo_root / p).resolve()
        else:
            p = p.resolve()
        rel = p.relative_to(repo_root.resolve())
        return bool(rel.parts) and rel.parts[0] in ("tests", "test")
    except ValueError:
        return bool(re.search(r"(^|/)(tests|test)/", path_str))


def tests_are_frozen(repo_root: pathlib.Path) -> bool:
    candidates = [
        repo_root / ".git" / "frozen_tests.sha256",
        repo_root / ".agents" / "state" / "frozen_tests.sha256",
        repo_root / ".gemini" / "frozen_tests.sha256",
        repo_root / ".frozen_tests.sha256",
    ]
    return any(p.is_file() for p in candidates)


def check_command(cmd: str, repo_root: pathlib.Path) -> None:
    # 1. Hard deny: reading secret files (.env, *.env, etc.)
    cleaned = re.sub(r"\.env\.(example|sample|template|schema)\b", "", cmd)
    env_read_pattern = re.compile(
        r"(^|[\s;|&`'\"(/])\.env(\b|\.[a-zA-Z0-9_-]+)|(^|[\s;|&`'\"(/])[a-zA-Z0-9_.-]+\.env(\b|[\s;|&`'\"/)])"
    )
    if env_read_pattern.search(cleaned):
        respond("deny", "Обращение к файлам секретов (.env) запрещено правилами безопасности.")

    # 2. If tests are frozen, block shell writes/redirections or git checkout/restore on tests/
    if tests_are_frozen(repo_root):
        if re.search(r"(>|>>|\btee\b|\bsed\s+-i|\brm\b|\bmv\b|\bcp\b).*(\b|/)(tests|test)/", cmd):
            respond(
                "deny",
                "Тесты заморожены. Изменение тестовых файлов запрещено правилами двух сессий.",
            )

    # 3. Force ask: git commit or git push
    if re.search(r"\bgit\s+commit\b", cmd):
        respond(
            "force_ask",
            "По правилам процесса коммиты делает владелец. Подтвердите выполнение git commit.",
        )
    if re.search(r"\bgit\s+push\b", cmd):
        respond(
            "force_ask",
            "Отправка изменений (git push) требует подтверждения владельца.",
        )

    # 4. Force ask: server state mutations via ssh
    if re.search(r"\bssh\b", cmd):
        server_mutation = re.compile(
            r"\bsystemctl\s+(start|stop|restart|reload|enable|disable|mask|unmask)\b"
            r"|\b(rm|mv|cp|tee|dd|install|chmod|chown)\b[^\n;|&]*/(etc/|opt/|var/)"
            r"|\bdeploy/(deploy|safe-restart|restart)\.sh"
        )
        if server_mutation.search(cmd):
            respond(
                "force_ask",
                "Команда меняет состояние службы или системных файлов на сервере. Требуется подтверждение владельца.",
            )


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        respond("allow")
        return

    repo_root = get_repo_root(data)
    tool_call = data.get("toolCall") or {}
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args") or {}

    if tool_name in ("read_file", "view_file"):
        target_path = args.get("Path") or args.get("AbsolutePath") or args.get("file_path") or ""
        if is_env_secret_path(target_path):
            respond("deny", "Чтение файлов секретов (.env) запрещено правилами безопасности.")
        respond("allow")

    if tool_name in ("edit_file", "write_file", "replace_file_content", "write_to_file"):
        target_path = (
            args.get("Path")
            or args.get("TargetFile")
            or args.get("AbsolutePath")
            or args.get("file_path")
            or ""
        )
        if is_env_secret_path(target_path):
            respond("deny", "Изменение файлов секретов (.env) запрещено правилами безопасности.")
        if is_test_path(target_path, repo_root) and tests_are_frozen(repo_root):
            respond(
                "deny",
                "Тесты заморожены. Автор реализации не имеет права изменять тестовые файлы.",
            )
        respond("allow")

    if tool_name == "run_command":
        cmd = args.get("CommandLine") or args.get("command") or ""
        check_command(cmd, repo_root)
        respond("allow")

    respond("allow")


if __name__ == "__main__":
    main()
