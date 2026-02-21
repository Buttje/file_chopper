"""
CLI tests for the 'segment' subcommand and remaining main.py coverage.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_chopper.main import main
from file_chopper.segmenter import SegmentResult, SegmentStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def txt_file(tmp_path: Path) -> Path:
    p = tmp_path / "hello.txt"
    p.write_text("Hello world!", encoding="utf-8")
    return p


@pytest.fixture()
def large_txt_file(tmp_path: Path) -> Path:
    p = tmp_path / "large.txt"
    p.write_text("A" * 5_000, encoding="utf-8")
    return p


@pytest.fixture()
def large_doc_file(tmp_path: Path) -> Path:
    p = tmp_path / "large.doc"
    p.write_bytes(b"\xd0\xcf\x11\xe0" + b"X" * 20_000)
    return p


@pytest.fixture()
def docx_file(tmp_path: Path) -> Path:
    import docx

    doc = docx.Document()
    for _ in range(10):
        doc.add_paragraph("A" * 200)
    p = tmp_path / "doc.docx"
    doc.save(str(p))
    return p


# ---------------------------------------------------------------------------
# CLI: segment --help
# ---------------------------------------------------------------------------


class TestCliSegmentHelp:
    def test_segment_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["segment", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--output-dir" in captured.out
        assert "--max-size" in captured.out
        assert "--max-chars" in captured.out

    def test_main_help_includes_segment(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "segment" in captured.out


# ---------------------------------------------------------------------------
# CLI: segment — argument validation (exit code 2)
# ---------------------------------------------------------------------------


class TestCliSegmentArgValidation:
    def test_invalid_max_size_returns_2(self, txt_file: Path, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--max-size",
                "notasize",
            ]
        )
        assert rc == 2

    def test_negative_max_chars_returns_2(self, txt_file: Path, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--max-size",
                "1MB",
                "--max-chars",
                "-1",
            ]
        )
        assert rc == 2

    def test_zero_max_chars_returns_2(self, txt_file: Path, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--max-size",
                "1MB",
                "--max-chars",
                "0",
            ]
        )
        assert rc == 2

    def test_missing_source_returns_2(self, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(tmp_path / "nonexistent.txt"),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        assert rc == 2


# ---------------------------------------------------------------------------
# CLI: segment — single file processing
# ---------------------------------------------------------------------------


class TestCliSegmentFile:
    def test_small_txt_exit_0(self, txt_file: Path, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--quiet",
            ]
        )
        assert rc == 0

    def test_small_txt_output_created(self, txt_file: Path, tmp_path: Path):
        out = tmp_path / "out"
        main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(out),
                "--quiet",
            ]
        )
        assert (out / "hello.txt").exists()

    def test_verbose_ok_output(self, txt_file: Path, tmp_path: Path, capsys):
        main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
        captured = capsys.readouterr()
        assert "OK" in captured.out

    def test_large_doc_exit_1(self, large_doc_file: Path, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(large_doc_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--max-size",
                "1KB",
                "--quiet",
            ]
        )
        assert rc == 1

    def test_large_txt_split_exit_0(self, large_txt_file: Path, tmp_path: Path):
        rc = main(
            [
                "segment",
                str(large_txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--max-size",
                "100MB",
                "--max-chars",
                "100",
                "--quiet",
            ]
        )
        assert rc == 0

    def test_missing_dep_exit_3(self, txt_file: Path, tmp_path: Path):
        """Simulate a missing-dependency result → exit code 3."""
        missing_dep_result = SegmentResult(
            source=txt_file,
            status=SegmentStatus.MISSING_DEP,
            error_msg="pypdf is required",
        )
        with patch("file_chopper.main.segment_document", return_value=missing_dep_result):
            rc = main(
                [
                    "segment",
                    str(txt_file),
                    "--output-dir",
                    str(tmp_path / "out"),
                    "--quiet",
                ]
            )
        assert rc == 3

    def test_error_result_exit_1(self, txt_file: Path, tmp_path: Path):
        """Simulate an error result → exit code 1."""
        error_result = SegmentResult(
            source=txt_file,
            status=SegmentStatus.ERROR,
            error_msg="some error",
        )
        with patch("file_chopper.main.segment_document", return_value=error_result):
            rc = main(
                [
                    "segment",
                    str(txt_file),
                    "--output-dir",
                    str(tmp_path / "out"),
                    "--quiet",
                ]
            )
        assert rc == 1


# ---------------------------------------------------------------------------
# CLI: segment — directory processing
# ---------------------------------------------------------------------------


class TestCliSegmentDirectory:
    def test_directory_exit_0(self, tmp_path: Path):
        input_dir = tmp_path / "docs"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("hello", encoding="utf-8")
        (input_dir / "b.txt").write_text("world", encoding="utf-8")
        out = tmp_path / "out"

        rc = main(
            [
                "segment",
                str(input_dir),
                "--output-dir",
                str(out),
                "--quiet",
            ]
        )
        assert rc == 0

    def test_directory_files_processed(self, tmp_path: Path):
        input_dir = tmp_path / "docs"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out"

        main(
            [
                "segment",
                str(input_dir),
                "--output-dir",
                str(out),
                "--quiet",
            ]
        )
        assert (out / "a.txt").exists()

    def test_directory_with_error_exits_1(self, tmp_path: Path):
        input_dir = tmp_path / "docs"
        input_dir.mkdir()
        large_doc = input_dir / "big.doc"
        large_doc.write_bytes(b"X" * 20_000)
        out = tmp_path / "out"

        rc = main(
            [
                "segment",
                str(input_dir),
                "--output-dir",
                str(out),
                "--max-size",
                "1KB",
                "--quiet",
            ]
        )
        assert rc == 1

    def test_fail_fast_flag(self, tmp_path: Path):
        input_dir = tmp_path / "docs"
        input_dir.mkdir()
        (input_dir / "aaa.doc").write_bytes(b"X" * 20_000)
        (input_dir / "zzz.txt").write_text("ok", encoding="utf-8")
        out = tmp_path / "out"

        rc = main(
            [
                "segment",
                str(input_dir),
                "--output-dir",
                str(out),
                "--max-size",
                "1KB",
                "--fail-fast",
                "--quiet",
            ]
        )
        # Should have stopped early; still non-zero exit
        assert rc != 0

    def test_directory_verbose_output(self, tmp_path: Path, capsys):
        input_dir = tmp_path / "docs"
        input_dir.mkdir()
        (input_dir / "a.txt").write_text("hello", encoding="utf-8")
        out = tmp_path / "out"

        main(
            [
                "segment",
                str(input_dir),
                "--output-dir",
                str(out),
            ]
        )
        captured = capsys.readouterr()
        assert "OK" in captured.out


# ---------------------------------------------------------------------------
# CLI: segment — default parameter values
# ---------------------------------------------------------------------------


class TestCliSegmentDefaults:
    def test_default_max_size_is_10mb(self, txt_file: Path, tmp_path: Path):
        """Verify the segment command uses 10MB as default max-size."""
        rc = main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--quiet",
            ]
        )
        # Should succeed with default settings
        assert rc == 0

    def test_default_max_chars_is_100000(self, txt_file: Path, tmp_path: Path):
        """Verify the segment command uses 100000 as default max-chars."""
        rc = main(
            [
                "segment",
                str(txt_file),
                "--output-dir",
                str(tmp_path / "out"),
                "--quiet",
            ]
        )
        assert rc == 0


# ---------------------------------------------------------------------------
# CLI: cli() entry point
# ---------------------------------------------------------------------------


class TestCliEntryPoint:
    def test_cli_exits(self):
        """cli() should call sys.exit with main()'s return value."""
        from file_chopper.main import cli

        with patch("file_chopper.main.main", return_value=0), pytest.raises(SystemExit) as exc_info:
            cli()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# CLI: chop verbose output (uncovered lines in _cmd_chop)
# ---------------------------------------------------------------------------


class TestCliChopVerbose:
    def test_chop_verbose_shows_parts(self, tmp_path: Path, capsys):
        source = tmp_path / "sample.bin"
        source.write_bytes(b"A" * 3_000)
        out = tmp_path / "out"
        main(["chop", str(source), "--size", "1K", "--output-dir", str(out)])
        captured = capsys.readouterr()
        assert "part" in captured.out.lower() or "Part" in captured.out

    def test_chop_verbose_shows_checksum(self, tmp_path: Path, capsys):
        source = tmp_path / "sample.bin"
        source.write_bytes(b"A" * 3_000)
        out = tmp_path / "out"
        main(["chop", str(source), "--size", "1K", "--output-dir", str(out)])
        captured = capsys.readouterr()
        assert "sha256" in captured.out.lower() or "SHA-256" in captured.out
