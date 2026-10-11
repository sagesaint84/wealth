"""Shared model is importable without a browser; no financial files involved."""
from pathlib import Path
import subprocess


def test_shared_color_model_node():
    result = subprocess.run(['node', '--test', 'tests/color-system.test.cjs'],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, encoding='utf-8')
    assert result.returncode == 0, result.stdout + result.stderr
