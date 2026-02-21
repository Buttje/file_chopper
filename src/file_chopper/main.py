"""
Command-line interface for file_chopper.

Entry point: ``file_chopper`` (defined in pyproject.toml console_scripts).
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path
from typing import List, Optional

from file_chopper import __version__
from file_chopper.chopper import (
    chop,
    find_parts,
    format_size,
    join,
    parse_size,
)
from file_chopper.segmenter import (
    SegmentStatus,
    segment_document,
)

# ---------------------------------------------------------------------------
# Optional progress bar (tqdm).  Falls back gracefully if not installed.
# ---------------------------------------------------------------------------

try:
    from tqdm import tqdm as _tqdm  # type: ignore[import-untyped]

    def _make_progress_cb(description: str, total: int):  # type: ignore[return]
        bar = _tqdm(
            total=total,
            unit="B",
            unit_scale=True,
            unit_divisor=1024,
            desc=description,
            dynamic_ncols=True,
        )
        _prev = [0]

        def _cb(done: int, _total: int) -> None:
            bar.update(done - _prev[0])
            _prev[0] = done
            if done >= _total:
                bar.close()

        return _cb

except ImportError:  # pragma: no cover

    def _make_progress_cb(description: str, total: int):  # type: ignore[return]
        def _cb(done: int, _total: int) -> None:
            pct = done / _total * 100 if _total else 0
            print(f"\r{description}: {pct:.1f}%", end="", flush=True)
            if done >= _total:
                print()

        return _cb


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="file_chopper",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            file_chopper — Split large files into smaller pieces and rejoin them.

            Common workflows
            ────────────────
              Split a 2 GB ISO into 700 MB pieces:
                  file_chopper chop big_file.iso --size 700MB

              Rejoin the pieces:
                  file_chopper join big_file.iso.part0001

              Segment documents for Fess:
                  file_chopper segment /data/docs --output-dir /output

              List how many parts a file will produce:
                  file_chopper chop big_file.iso --size 700MB --dry-run
            """
        ),
        epilog=textwrap.dedent(
            """\
            Size units
            ──────────
              B   bytes
              K / KB   kibibytes  (1 024 B)
              M / MB   mebibytes  (1 024 KB)
              G / GB   gibibytes  (1 024 MB)
              T / TB   tebibytes  (1 024 GB)

            Exit codes
            ──────────
              0   success
              1   completed with errors (at least one file failed)
              2   configuration/argument error
              3   missing Python dependency
            """
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    subparsers.required = True

    # ---- chop ---------------------------------------------------------------
    chop_parser = subparsers.add_parser(
        "chop",
        help="Split a file into smaller pieces.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Split FILE into chunks of at most SIZE bytes.

            Each chunk is written as FILE.partNNNN (e.g. movie.mkv.part0001).
            A SHA-256 checksum file (FILE.sha256) is also created so that
            'file_chopper join' can verify integrity after reassembly.

            Examples
            ────────
              Split into 100 MB pieces (output next to the source file):
                  file_chopper chop archive.tar.gz --size 100MB

              Split into 1 GB pieces and save to /tmp:
                  file_chopper chop backup.tar --size 1G --output-dir /tmp

              Preview without writing anything:
                  file_chopper chop big.iso --size 700MB --dry-run
            """
        ),
    )
    chop_parser.add_argument(
        "file",
        metavar="FILE",
        help="Path to the file you want to split.",
    )
    chop_parser.add_argument(
        "--size",
        "-s",
        required=True,
        metavar="SIZE",
        help=(
            "Maximum size of each piece.  "
            "Accepts a number with an optional unit, e.g. '100MB', '700K', '2G'."
        ),
    )
    chop_parser.add_argument(
        "--output-dir",
        "-o",
        metavar="DIR",
        default=None,
        help="Directory where piece files are written (default: same directory as FILE).",
    )
    chop_parser.add_argument(
        "--no-verify",
        action="store_true",
        default=False,
        help="Skip writing the SHA-256 checksum file.",
    )
    chop_parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        default=False,
        help="Show what would be done without writing any files.",
    )
    chop_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress progress output.",
    )

    # ---- join ---------------------------------------------------------------
    join_parser = subparsers.add_parser(
        "join",
        help="Reassemble pieces back into the original file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Reassemble piece files produced by 'file_chopper chop'.

            You can supply either:
              • A single .partNNNN file — all sibling parts are found automatically.
              • A directory           — the directory is searched for .partNNNN files.
              • An explicit list of .partNNNN files in the desired order.

            Examples
            ────────
              Auto-discover parts next to the first part file:
                  file_chopper join archive.tar.gz.part0001

              Auto-discover parts in a directory:
                  file_chopper join /tmp/parts/ --base archive.tar.gz

              Write output to a specific location:
                  file_chopper join archive.tar.gz.part0001 --output /data/archive.tar.gz
            """
        ),
    )
    join_parser.add_argument(
        "parts",
        nargs="+",
        metavar="PART",
        help=(
            "One or more .partNNNN files, OR a single directory "
            "(combined with --base to identify which file to join)."
        ),
    )
    join_parser.add_argument(
        "--output",
        "-o",
        metavar="FILE",
        default=None,
        help=(
            "Path for the reassembled output file.  "
            "Inferred from the part name when omitted."
        ),
    )
    join_parser.add_argument(
        "--base",
        "-b",
        metavar="NAME",
        default=None,
        help=(
            "Base file name to search for when PART is a directory "
            "(e.g. '--base archive.tar.gz')."
        ),
    )
    join_parser.add_argument(
        "--no-verify",
        action="store_true",
        default=False,
        help="Skip SHA-256 integrity verification after reassembly.",
    )
    join_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress progress output.",
    )

    # ---- segment ------------------------------------------------------------
    seg_parser = subparsers.add_parser(
        "segment",
        help="Segment large documents for Fess filesystem crawl.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """\
            Split large source documents into smaller child documents and
            prepare an output folder structure suitable for a Fess filesystem crawl.

            Supported formats: .pdf .txt .csv .md .html .htm .docx .pptx .xlsx
                               .odt .odp .ods .rtf

            Out-of-scope formats (.doc .ppt .xls):
              - If no split is required: copied unchanged (exit 0).
              - If split is required:    marked as error (exit 1).

            Examples
            ────────
              Segment all documents in /data/docs into /output:
                  file_chopper segment /data/docs --output-dir /output

              Segment a single file with custom limits:
                  file_chopper segment report.docx --output-dir /output \\
                      --max-size 5MB --max-chars 50000
            """
        ),
    )
    seg_parser.add_argument(
        "source",
        metavar="SOURCE",
        help="Path to a file or directory to segment.",
    )
    seg_parser.add_argument(
        "--output-dir",
        "-o",
        metavar="DIR",
        required=True,
        help="Directory where segmented output files are written.",
    )
    seg_parser.add_argument(
        "--max-size",
        metavar="SIZE",
        default="10MB",
        help=(
            "Maximum size of each child document in bytes (default: 10MB).  "
            "Splitting is triggered when the source exceeds this value."
        ),
    )
    seg_parser.add_argument(
        "--max-chars",
        metavar="N",
        type=int,
        default=100_000,
        help=(
            "Maximum number of extracted text characters per child document "
            "(default: 100000).  Splitting is triggered when the source exceeds this."
        ),
    )
    seg_parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="Stop processing after the first error.",
    )
    seg_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress progress output.",
    )

    return parser


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def _cmd_chop(args: argparse.Namespace) -> int:
    source = Path(args.file)

    try:
        chunk_size = parse_size(args.size)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir) if args.output_dir else None

    if not source.exists():
        print(
            f"Error: File not found: '{source}'\n"
            "Please check the path and try again.",
            file=sys.stderr,
        )
        return 1
    if source.is_dir():
        print(
            f"Error: '{source}' is a directory, not a file.\n"
            "file_chopper can only split individual files.",
            file=sys.stderr,
        )
        return 1

    file_size = source.stat().st_size
    if file_size == 0:
        print(f"Error: '{source}' is empty (0 bytes). Nothing to split.", file=sys.stderr)
        return 1

    num_parts = (file_size + chunk_size - 1) // chunk_size
    dest = output_dir or source.parent

    print(
        f"  Source     : {source}  ({format_size(file_size)})\n"
        f"  Chunk size : {format_size(chunk_size)}\n"
        f"  Parts      : {num_parts}\n"
        f"  Output dir : {dest}"
    )

    if args.dry_run:
        print("\nDry-run mode — no files written.")
        for i in range(1, num_parts + 1):
            part_name = source.name + f".part{i:04d}"
            size = chunk_size if i < num_parts else file_size - (num_parts - 1) * chunk_size
            print(f"  Would create: {dest / part_name}  ({format_size(size)})")
        return 0

    progress_cb = (
        None
        if args.quiet
        else _make_progress_cb(f"Chopping '{source.name}'", file_size)
    )

    try:
        parts = chop(
            source=source,
            chunk_size=chunk_size,
            output_dir=output_dir,
            progress_cb=progress_cb,
            verify=not args.no_verify,
        )
    except (FileNotFoundError, IsADirectoryError, ValueError, OSError) as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"\nCreated {len(parts)} part(s):")
        for p in parts:
            print(f"  {p}  ({format_size(p.stat().st_size)})")
        if not args.no_verify:
            checksum_path = (output_dir or source.parent) / (source.name + ".sha256")
            print(f"  {checksum_path}  (SHA-256 checksum)")

    return 0


def _cmd_join(args: argparse.Namespace) -> int:
    raw_parts: List[str] = args.parts

    # Resolve the list of part files
    if len(raw_parts) == 1 and Path(raw_parts[0]).is_dir():
        # User passed a directory
        directory = Path(raw_parts[0])
        if not args.base:
            print(
                "Error: When supplying a directory you must also provide --base <filename>.\n"
                "Example: file_chopper join /tmp/parts/ --base archive.tar.gz",
                file=sys.stderr,
            )
            return 1
        try:
            part_paths = find_parts(directory, args.base)
        except FileNotFoundError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
    else:
        # One or more explicit part files (or the first .partNNNN from which
        # we discover siblings automatically)
        if (
            len(raw_parts) == 1
            and not Path(raw_parts[0]).is_dir()
            and ".part" in raw_parts[0]
        ):
            first = Path(raw_parts[0])
            # Extract base name and discover all sibling parts
            from file_chopper.chopper import PART_PATTERN

            m = PART_PATTERN.match(first.name)
            if m:
                base_name = m.group(1)
                try:
                    part_paths = find_parts(first.parent, base_name)
                except FileNotFoundError as exc:
                    print(f"Error: {exc}", file=sys.stderr)
                    return 1
            else:
                part_paths = [first]
        else:
            part_paths = [Path(p) for p in raw_parts]

    output = Path(args.output) if args.output else None

    total_bytes = 0
    for p in part_paths:
        if not p.exists():
            print(
                f"Error: Part file not found: '{p}'\n"
                "Make sure all part files are present before joining.",
                file=sys.stderr,
            )
            return 1
        total_bytes += p.stat().st_size

    if not args.quiet:
        print(
            f"  Parts      : {len(part_paths)}\n"
            f"  Total size : {format_size(total_bytes)}\n"
            f"  Output     : {output or '(inferred from part name)'}"
        )

    progress_cb = (
        None
        if args.quiet
        else _make_progress_cb("Joining", total_bytes)
    )

    try:
        out_path = join(
            parts=part_paths,
            output=output,
            progress_cb=progress_cb,
            verify=not args.no_verify,
        )
    except FileNotFoundError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"\nError: {exc}", file=sys.stderr)
        return 1

    if not args.quiet:
        print(f"\nReassembled file: {out_path}  ({format_size(out_path.stat().st_size)})")
        if not args.no_verify:
            from file_chopper.chopper import PART_PATTERN as _PP

            m = _PP.match(part_paths[0].name)
            checksum_name = (m.group(1) if m else out_path.name) + ".sha256"
            checksum_path = part_paths[0].parent / checksum_name
            if checksum_path.exists():
                print("  ✓ Integrity check passed (SHA-256)")
            else:
                print("  ⚠ No checksum file found — integrity not verified.")

    return 0


# ---------------------------------------------------------------------------
# Segment command handler
# ---------------------------------------------------------------------------


def _cmd_segment(args: argparse.Namespace) -> int:
    source = Path(args.source)

    try:
        max_child_bytes = parse_size(args.max_size)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.max_chars <= 0:
        print("Error: --max-chars must be a positive integer.", file=sys.stderr)
        return 2

    if not source.exists():
        print(
            f"Error: Source not found: '{source}'\n"
            "Please check the path and try again.",
            file=sys.stderr,
        )
        return 2

    output_dir = Path(args.output_dir)

    if source.is_dir():
        from file_chopper.segmenter import segment_folder

        results = segment_folder(
            input_dir=source,
            output_dir=output_dir,
            max_child_bytes=max_child_bytes,
            max_child_text_chars=args.max_chars,
            fail_fast=args.fail_fast,
        )
    else:
        result = segment_document(
            source=source,
            output_dir=output_dir,
            max_child_bytes=max_child_bytes,
            max_child_text_chars=args.max_chars,
        )
        results = [result]

    errors = 0
    missing_deps = 0
    for result in results:
        if result.status == SegmentStatus.OK:
            if not args.quiet:
                children_str = ", ".join(str(c) for c in result.children)
                print(f"  OK  {result.source} -> [{children_str}]")
        elif result.status == SegmentStatus.MISSING_DEP:
            missing_deps += 1
            print(f"Error (missing dependency): {result.error_msg}", file=sys.stderr)
        else:
            errors += 1
            print(f"Error: {result.error_msg}", file=sys.stderr)

    if missing_deps:
        return 3
    if errors:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    """Parse arguments and dispatch to the appropriate sub-command handler.

    Parameters
    ----------
    argv:
        Argument list; defaults to :data:`sys.argv[1:]` when *None*.

    Returns
    -------
    int
        Exit code (0 = success, 1 = completed with errors,
        2 = configuration/argument error, 3 = missing dependency).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "chop":
        return _cmd_chop(args)
    if args.command == "join":
        return _cmd_join(args)
    if args.command == "segment":
        return _cmd_segment(args)

    parser.print_help()
    return 1


def cli() -> None:
    """Console-script entry point."""
    sys.exit(main())


if __name__ == "__main__":
    cli()
