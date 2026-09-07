from __future__ import annotations

import fnmatch
import unittest
from pathlib import Path, PurePosixPath


ROOT_DIR = Path(__file__).resolve().parents[1]


def dockerignore_patterns() -> list[str]:
    return [
        line.strip()
        for line in (ROOT_DIR / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def representative_path_is_ignored(path: str, patterns: list[str]) -> bool:
    normalized = PurePosixPath(path).as_posix()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    normalized = normalized.lstrip("/")
    ignored = False
    for raw_pattern in patterns:
        negate = raw_pattern.startswith("!")
        pattern = raw_pattern[1:] if negate else raw_pattern
        pattern = pattern.lstrip("/")
        directory_pattern = pattern.endswith("/")
        pattern = pattern.rstrip("/")

        if directory_pattern:
            matched = normalized == pattern or normalized.startswith(f"{pattern}/")
            if pattern.startswith("**/"):
                segment = pattern[3:]
                matched = segment in normalized.split("/")
        elif pattern.startswith("**/"):
            matched = fnmatch.fnmatch(normalized, pattern[3:]) or fnmatch.fnmatch(normalized, pattern)
        elif "/" not in pattern:
            matched = any(fnmatch.fnmatch(part, pattern) for part in normalized.split("/"))
        else:
            matched = fnmatch.fnmatch(normalized, pattern)

        if matched:
            ignored = not negate
    return ignored


class DockerIgnoreSecurityTests(unittest.TestCase):
    def test_sensitive_and_temporary_files_are_excluded(self) -> None:
        patterns = dockerignore_patterns()
        excluded_paths = (
            ".env",
            ".env.production",
            "data/portfolio.json",
            "private-assets.xlsx",
            "imports/private-assets.xls",
            "exports/private-assets.csv",
            "scratch/note.txt",
            "app/__pycache__/main.cpython-314.pyc",
            ".git/config",
            ".vscode/settings.json",
            ".idea/workspace.xml",
            ".pytest_cache/v/cache/nodeids",
            ".mypy_cache/3.14/cache.json",
            "debug.log",
            "backup/portfolio.json",
            "backups/portfolio.json",
            "wealth_user_a_2026-01-02.json",
            "portfolio-backup-2026.json",
            "portfolio.bak",
            "local.sqlite3",
            "secrets/server.pem",
            "credentials/api-credentials.json",
            "temporary.tmp",
            ".DS_Store",
            "Thumbs.db",
        )
        for path in excluded_paths:
            with self.subTest(path=path):
                self.assertTrue(representative_path_is_ignored(path, patterns), path)

    def test_runtime_sources_and_documentation_remain_in_build_context(self) -> None:
        patterns = dockerignore_patterns()
        included_paths = (
            "Dockerfile",
            "README.md",
            "requirements.txt",
            "app/main.py",
            "app/static/app.js",
        )
        for path in included_paths:
            with self.subTest(path=path):
                self.assertFalse(representative_path_is_ignored(path, patterns), path)


if __name__ == "__main__":
    unittest.main()
