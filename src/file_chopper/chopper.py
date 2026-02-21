"""
Core file splitting and joining logic for file_chopper.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PART_SUFFIX_TEMPLATE = ".part{index:04d}"
PART_PATTERN = re.compile(r"^(.+)\.part(\d{4})$")

# Default read/write buffer size (4 MiB)
BUFFER_SIZE = 4 * 1024 * 1024


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def parse_size(size_str: str) -> int:
    """Convert a human-readable size string to bytes.

    Accepted formats (case-insensitive):
        ``512``, ``512B``, ``10K``, ``10KB``, ``5M``, ``5MB``, ``2G``, ``2GB``

    Parameters
    ----------
    size_str:
        Human-readable size string.

    Returns
    -------
    int
        Number of bytes represented by *size_str*.

    Raises
    ------
    ValueError
        When *size_str* cannot be parsed.
    """
    size_str = size_str.strip()
    units = {
        "B": 1,
        "K": 1024,
        "KB": 1024,
        "M": 1024**2,
        "MB": 1024**2,
        "G": 1024**3,
        "GB": 1024**3,
        "T": 1024**4,
        "TB": 1024**4,
    }
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z]*)", size_str)
    if not match:
        raise ValueError(
            f"Cannot parse size '{size_str}'. "
            "Use a number optionally followed by a unit, e.g. '100MB', '2G', '512K'."
        )
    number_str, unit = match.group(1), match.group(2).upper()
    if unit == "":
        unit = "B"
    if unit not in units:
        raise ValueError(
            f"Unknown size unit '{unit}'. "
            f"Supported units: {', '.join(units.keys())}."
        )
    return int(float(number_str) * units[unit])


def format_size(num_bytes: int) -> str:
    """Return a human-readable representation of *num_bytes*."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes //= 1024
    return f"{num_bytes} B"  # unreachable but satisfies type checkers


def sha256_of_file(path: Path) -> str:
    """Return the SHA-256 hex digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(BUFFER_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Progress callback type
# ---------------------------------------------------------------------------

# A callable that receives (bytes_done, total_bytes).  Implementations may
# display a progress bar or simply be a no-op.
ProgressCallback = Optional[object]  # callable[[int, int], None]


def _null_progress(done: int, total: int) -> None:
    """No-op progress callback."""


# ---------------------------------------------------------------------------
# Chop
# ---------------------------------------------------------------------------


def chop(
    source: Path,
    chunk_size: int,
    output_dir: Optional[Path] = None,
    progress_cb: ProgressCallback = None,
    verify: bool = True,
) -> List[Path]:
    """Split *source* into chunks of at most *chunk_size* bytes.

    Parameters
    ----------
    source:
        Path to the file to split.
    chunk_size:
        Maximum size of each output chunk in bytes.
    output_dir:
        Directory where chunk files are written.  Defaults to the directory
        that contains *source*.
    progress_cb:
        Optional callable ``(bytes_done: int, total_bytes: int) -> None``
        invoked after each chunk is written.
    verify:
        When ``True`` a SHA-256 checksum file is written alongside the parts
        so that :func:`join` can verify integrity.

    Returns
    -------
    list[Path]
        Ordered list of paths to the created chunk files.

    Raises
    ------
    FileNotFoundError
        When *source* does not exist.
    ValueError
        When *chunk_size* is not positive.
    IsADirectoryError
        When *source* is a directory.
    """
    source = Path(source)
    if not source.exists():
        raise FileNotFoundError(
            f"Source file not found: '{source}'\n"
            "Please check the path and try again."
        )
    if source.is_dir():
        raise IsADirectoryError(
            f"'{source}' is a directory, not a file.\n"
            "file_chopper can only split individual files."
        )
    if chunk_size <= 0:
        raise ValueError(
            f"Chunk size must be a positive number of bytes, got {chunk_size}."
        )

    total_bytes = source.stat().st_size
    if total_bytes == 0:
        raise ValueError(
            f"'{source}' is empty (0 bytes). Nothing to split."
        )

    if output_dir is None:
        output_dir = source.parent
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cb = progress_cb if callable(progress_cb) else _null_progress

    parts: List[Path] = []
    index = 1
    bytes_done = 0

    with source.open("rb") as src_fh:
        while True:
            data = src_fh.read(chunk_size)
            if not data:
                break
            part_path = output_dir / (source.name + PART_SUFFIX_TEMPLATE.format(index=index))
            with part_path.open("wb") as out_fh:
                out_fh.write(data)
            parts.append(part_path)
            bytes_done += len(data)
            cb(bytes_done, total_bytes)
            index += 1

    if verify:
        checksum = sha256_of_file(source)
        checksum_path = output_dir / (source.name + ".sha256")
        checksum_path.write_text(f"{checksum}  {source.name}\n", encoding="utf-8")

    return parts


# ---------------------------------------------------------------------------
# Join
# ---------------------------------------------------------------------------


def join(
    parts: List[Path],
    output: Optional[Path] = None,
    progress_cb: ProgressCallback = None,
    verify: bool = True,
) -> Path:
    """Reassemble *parts* into the original file.

    Parts are written in the order they are supplied in the *parts* list.
    Use :func:`find_parts` to obtain a correctly-ordered list from a
    directory.

    Parameters
    ----------
    parts:
        Ordered list of chunk file paths produced by :func:`chop`.
    output:
        Path for the reassembled output file.  When omitted the base name is
        inferred from the first part's name (strips the ``.partNNNN`` suffix)
        and the file is placed in the same directory as the parts.
    progress_cb:
        Optional callable ``(bytes_done: int, total_bytes: int) -> None``.
    verify:
        When ``True`` the SHA-256 checksum file (if present) is used to
        verify that the reassembled file matches the original.

    Returns
    -------
    Path
        Path to the reassembled output file.

    Raises
    ------
    FileNotFoundError
        When any of the supplied *parts* do not exist.
    ValueError
        When *parts* is empty.
    """
    if not parts:
        raise ValueError(
            "No part files supplied.  "
            "Use 'file_chopper join <directory>' or list the .partNNNN files explicitly."
        )

    parts = [Path(p) for p in parts]
    for part in parts:
        if not part.exists():
            raise FileNotFoundError(
                f"Part file not found: '{part}'\n"
                "Make sure all part files are present before joining."
            )

    total_bytes = sum(p.stat().st_size for p in parts)
    cb = progress_cb if callable(progress_cb) else _null_progress

    if output is None:
        first = parts[0]
        m = PART_PATTERN.match(first.name)
        if m:
            base_name = m.group(1)
        else:
            base_name = first.stem
        output = first.parent / base_name

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    bytes_done = 0
    with output.open("wb") as out_fh:
        for part in parts:
            with part.open("rb") as part_fh:
                while True:
                    data = part_fh.read(BUFFER_SIZE)
                    if not data:
                        break
                    out_fh.write(data)
                    bytes_done += len(data)
                    cb(bytes_done, total_bytes)

    if verify:
        # Locate the checksum file using the base name derived from the part
        # file names (e.g. "sample.bin.sha256"), NOT from the output file name,
        # because the caller may write the output to a different name.
        m = PART_PATTERN.match(parts[0].name)
        checksum_name = (m.group(1) if m else output.name) + ".sha256"
        checksum_path = parts[0].parent / checksum_name
        if checksum_path.exists():
            expected_line = checksum_path.read_text(encoding="utf-8").split()[0]
            actual = sha256_of_file(output)
            if actual != expected_line:
                output.unlink(missing_ok=True)
                raise ValueError(
                    f"Checksum mismatch!\n"
                    f"  Expected : {expected_line}\n"
                    f"  Got      : {actual}\n"
                    "The reassembled file has been removed.  "
                    "Ensure all part files are intact and retry."
                )

    return output


# ---------------------------------------------------------------------------
# Discovery helpers
# ---------------------------------------------------------------------------


def find_parts(directory: Path, base_name: str) -> List[Path]:
    """Return an ordered list of part files in *directory* for *base_name*.

    Parameters
    ----------
    directory:
        Directory to search.
    base_name:
        The original file name (e.g. ``"archive.tar.gz"``).

    Returns
    -------
    list[Path]
        Sorted list of matching ``.partNNNN`` files.

    Raises
    ------
    FileNotFoundError
        When no matching part files are found.
    """
    directory = Path(directory)
    pattern = f"{base_name}.part*"
    candidates = sorted(directory.glob(pattern))
    parts = [p for p in candidates if PART_PATTERN.match(p.name)]
    if not parts:
        raise FileNotFoundError(
            f"No part files found for '{base_name}' in '{directory}'.\n"
            f"Expected files matching '{base_name}.partNNNN'."
        )
    return parts

