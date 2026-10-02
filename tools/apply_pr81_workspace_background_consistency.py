from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAYOUT_CSS = ROOT / "app" / "static" / "wealth-layout.css"
MARKER = "/* Workspace background consistency across long tabs */"
BLOCK = """/* Workspace background consistency across long tabs */
body.wealth-layout {
  background-attachment: fixed;
}
"""


def main() -> None:
    source = LAYOUT_CSS.read_text(encoding="utf-8")
    if MARKER in source:
        print("PR81_WORKSPACE_BACKGROUND_ALREADY_PATCHED")
        return

    patched = source.rstrip("\r\n") + "\n\n" + BLOCK
    LAYOUT_CSS.write_text(patched, encoding="utf-8")
    print("PR81_WORKSPACE_BACKGROUND_PATCHED")


if __name__ == "__main__":
    main()
