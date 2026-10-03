import sysconfig
from pathlib import Path
import sys


def installed_puzzlepress() -> Path:
    scripts_dir = Path(sysconfig.get_path("scripts"))
    executable = scripts_dir / (
        "puzzlepress.exe" if sys.platform == "win32" else "puzzlepress"
    )

    assert executable.is_file(), (
        f"Installed PuzzlePress console script not found: {executable}"
    )

    return executable