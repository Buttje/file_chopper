#!/usr/bin/env python3
"""
install.py — Cross-platform installer for file_chopper
=======================================================

Supported platforms
-------------------
  * Windows 10 / Windows 11
  * Linux (any modern distribution)

What this script does
---------------------
  1. Verifies that Python 3.8+ is available.
  2. Creates a virtual environment in the ``.venv`` folder.
  3. Installs all runtime dependencies (tqdm, etc.) into the venv.
  4. Installs file_chopper itself into the venv in editable mode.
  5. Creates a platform-specific launcher:
       Windows  → ``run_file_chopper.bat``  (double-click or run from CMD)
       Linux    → ``run_file_chopper.sh``   (run as ./run_file_chopper.sh)
  6. Prints clear next-step instructions.

Usage
-----
  Windows:   python install.py
  Linux:     python3 install.py
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import textwrap
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MINIMUM_PYTHON = (3, 8)
VENV_DIR = Path(".venv")
SCRIPT_DIR = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _print_header(text: str) -> None:
    line = "=" * 60
    print(f"\n{line}\n  {text}\n{line}")


def _print_step(step: str, description: str) -> None:
    print(f"\n[{step}] {description}")


def _abort(message: str) -> None:
    print(f"\nERROR: {message}\n", file=sys.stderr)
    sys.exit(1)


def _run(args: list, **kwargs) -> subprocess.CompletedProcess:
    """Run a subprocess, stream output to the terminal, raise on failure."""
    print("  $", " ".join(str(a) for a in args))
    try:
        return subprocess.run(args, check=True, **kwargs)  # noqa: S603
    except subprocess.CalledProcessError as exc:
        _abort(
            f"Command failed with exit code {exc.returncode}.\n"
            f"Command: {' '.join(str(a) for a in args)}\n"
            "Please check the output above for details."
        )


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_python_version() -> None:
    _print_step("1/5", "Checking Python version")
    version = sys.version_info[:2]
    if version < MINIMUM_PYTHON:
        _abort(
            f"Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]}+ is required, "
            f"but you are running Python {version[0]}.{version[1]}.\n"
            "Please install a newer Python from https://www.python.org/downloads/"
        )
    print(f"  ✓ Python {sys.version.split()[0]} — OK")


# ---------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------


def create_venv() -> Path:
    _print_step("2/5", f"Creating virtual environment in '{VENV_DIR}'")

    if VENV_DIR.exists():
        print(f"  Virtual environment already exists at '{VENV_DIR}' — skipping creation.")
    else:
        _run([sys.executable, "-m", "venv", str(VENV_DIR)])
        print(f"  ✓ Virtual environment created at '{VENV_DIR}'")

    return VENV_DIR


def _venv_python(venv: Path) -> Path:
    """Return the path to the Python executable inside *venv*."""
    if platform.system() == "Windows":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _venv_pip(venv: Path) -> Path:
    """Return the path to the pip executable inside *venv*."""
    if platform.system() == "Windows":
        return venv / "Scripts" / "pip.exe"
    return venv / "bin" / "pip"


# ---------------------------------------------------------------------------
# Install dependencies
# ---------------------------------------------------------------------------


def upgrade_pip(venv: Path) -> None:
    _print_step("3/5", "Upgrading pip inside the virtual environment")
    _run([str(_venv_python(venv)), "-m", "pip", "install", "--upgrade", "pip"])
    print("  ✓ pip upgraded")


def install_package(venv: Path) -> None:
    _print_step("4/5", "Installing file_chopper and its dependencies")
    # Install in editable mode so the source tree is used directly.
    _run(
        [
            str(_venv_python(venv)),
            "-m",
            "pip",
            "install",
            "--editable",
            f"{SCRIPT_DIR}[dev]",
        ]
    )
    print("  ✓ file_chopper installed")


# ---------------------------------------------------------------------------
# Platform-specific launchers
# ---------------------------------------------------------------------------


def create_launcher(venv: Path) -> None:
    _print_step("5/5", "Creating platform launcher")

    system = platform.system()

    if system == "Windows":
        _create_windows_launcher(venv)
    else:
        _create_linux_launcher(venv)


def _create_windows_launcher(venv: Path) -> None:
    bat_path = SCRIPT_DIR / "run_file_chopper.bat"
    venv_python = venv / "Scripts" / "python.exe"
    content = textwrap.dedent(
        f"""\
        @echo off
        REM file_chopper launcher — generated by install.py
        "{venv_python}" -m file_chopper.main %*
        """
    )
    bat_path.write_text(content, encoding="utf-8")
    print(f"  ✓ Windows launcher created: {bat_path}")


def _create_linux_launcher(venv: Path) -> None:
    sh_path = SCRIPT_DIR / "run_file_chopper.sh"
    venv_python = venv / "bin" / "python"
    content = textwrap.dedent(
        f"""\
        #!/usr/bin/env bash
        # file_chopper launcher — generated by install.py
        exec "{venv_python}" -m file_chopper.main "$@"
        """
    )
    sh_path.write_text(content, encoding="utf-8")
    sh_path.chmod(sh_path.stat().st_mode | 0o111)  # make executable
    print(f"  ✓ Linux launcher created: {sh_path}")


# ---------------------------------------------------------------------------
# Final instructions
# ---------------------------------------------------------------------------


def print_instructions(venv: Path) -> None:
    system = platform.system()
    activate_cmd = (
        r".venv\Scripts\activate" if system == "Windows" else "source .venv/bin/activate"
    )
    run_cmd = (
        r"run_file_chopper.bat" if system == "Windows" else "./run_file_chopper.sh"
    )
    venv_chopper = (
        str(venv / "Scripts" / "file_chopper.exe")
        if system == "Windows"
        else str(venv / "bin" / "file_chopper")
    )

    print(
        textwrap.dedent(
            f"""
            ╔══════════════════════════════════════════════════════════╗
            ║          file_chopper installation complete!             ║
            ╚══════════════════════════════════════════════════════════╝

            You can now run file_chopper in one of these ways:

            Option 1 — Use the launcher script (no activation needed):
                {run_cmd} --help

            Option 2 — Activate the virtual environment first:
                {activate_cmd}
                file_chopper --help

            Option 3 — Use the venv binary directly:
                {venv_chopper} --help

            Quick examples:
                {run_cmd} chop large_file.bin --size 100MB
                {run_cmd} join large_file.bin.part0001
            """
        )
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    _print_header("file_chopper — Installation")

    os.chdir(SCRIPT_DIR)

    check_python_version()
    venv = create_venv()
    upgrade_pip(venv)
    install_package(venv)
    create_launcher(venv)
    print_instructions(venv)


if __name__ == "__main__":
    main()
