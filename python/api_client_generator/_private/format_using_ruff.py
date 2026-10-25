from __future__ import annotations

import shutil
import subprocess
import sysconfig
import warnings

from api_client_generator._private.common.defaults import DEFAULT_LINE_LENGTH_FOR_RUFF


def _find_ruff_bin() -> str | None:
    # Ruff is not a runtime dependency: prefer the one installed next to this interpreter, else the one on PATH.
    return shutil.which("ruff", path=sysconfig.get_path("scripts")) or shutil.which("ruff")


def format_using_ruff(code: str, line_length: int = DEFAULT_LINE_LENGTH_FOR_RUFF) -> str:
    """
    Format the given code using Ruff.

    Returns the code unchanged, with a warning, when Ruff is not installed; returns it unchanged when Ruff fails.
    """

    ruff_bin = _find_ruff_bin()
    if ruff_bin is None:
        warnings.warn("ruff not found; generated code is left unformatted", stacklevel=2)
        return code

    try:
        completed_process = subprocess.run(
            [
                ruff_bin,
                "format",
                "--config",
                f"line-length={line_length}",
                "--stdin-filename",
                "file.py",
                "-",
            ],
            check=True,
            capture_output=True,
            text=True,
            input=code,
        )
    except subprocess.CalledProcessError:
        return code
    else:
        return completed_process.stdout
