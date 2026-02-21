"""
Tests for file_chopper — core logic and CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_chopper.chopper import (
    chop,
    find_parts,
    format_size,
    join,
    parse_size,
    sha256_of_file,
)
from file_chopper.main import main


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_file(tmp_path: Path) -> Path:
    """A 10 KiB temporary file filled with known bytes."""
    p = tmp_path / "sample.bin"
    p.write_bytes(bytes(range(256)) * 40)  # 10 240 bytes
    return p


@pytest.fixture()
def tiny_file(tmp_path: Path) -> Path:
    """A 100-byte file."""
    p = tmp_path / "tiny.txt"
    p.write_bytes(b"A" * 100)
    return p


# ---------------------------------------------------------------------------
# parse_size
# ---------------------------------------------------------------------------


class TestParseSize:
    def test_plain_bytes(self):
        assert parse_size("512") == 512

    def test_bytes_suffix(self):
        assert parse_size("512B") == 512

    def test_kilobytes(self):
        assert parse_size("1K") == 1024
        assert parse_size("1KB") == 1024

    def test_megabytes(self):
        assert parse_size("1M") == 1024**2
        assert parse_size("1MB") == 1024**2

    def test_gigabytes(self):
        assert parse_size("2G") == 2 * 1024**3
        assert parse_size("2GB") == 2 * 1024**3

    def test_case_insensitive(self):
        assert parse_size("100mb") == 100 * 1024**2

    def test_decimal(self):
        assert parse_size("1.5K") == int(1.5 * 1024)

    def test_whitespace(self):
        assert parse_size("  10 MB  ") == 10 * 1024**2

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            parse_size("abc")

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown size unit"):
            parse_size("10XB")


# ---------------------------------------------------------------------------
# format_size
# ---------------------------------------------------------------------------


class TestFormatSize:
    def test_bytes(self):
        assert format_size(512) == "512 B"

    def test_kilobytes(self):
        assert "KB" in format_size(2048)

    def test_megabytes(self):
        assert "MB" in format_size(5 * 1024**2)


# ---------------------------------------------------------------------------
# chop
# ---------------------------------------------------------------------------


class TestChop:
    def test_splits_into_correct_number_of_parts(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=False)
        # 10 240 bytes / 1 024 = exactly 10 parts
        assert len(parts) == 10

    def test_parts_named_correctly(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=False)
        assert parts[0].name == "sample.bin.part0001"
        assert parts[-1].name == "sample.bin.part0010"

    def test_total_size_equals_source(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=3000, output_dir=tmp_path, verify=False)
        total = sum(p.stat().st_size for p in parts)
        assert total == tmp_file.stat().st_size

    def test_checksum_file_created(self, tmp_file: Path, tmp_path: Path):
        chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=True)
        checksum_path = tmp_path / "sample.bin.sha256"
        assert checksum_path.exists()
        content = checksum_path.read_text()
        assert len(content.split()[0]) == 64  # SHA-256 hex digest

    def test_no_checksum_when_verify_false(self, tmp_file: Path, tmp_path: Path):
        chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=False)
        checksum_path = tmp_path / "sample.bin.sha256"
        assert not checksum_path.exists()

    def test_source_not_found_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="not found"):
            chop(tmp_path / "ghost.bin", chunk_size=1024)

    def test_source_is_directory_raises(self, tmp_path: Path):
        with pytest.raises(IsADirectoryError):
            chop(tmp_path, chunk_size=1024)

    def test_zero_chunk_size_raises(self, tmp_file: Path):
        with pytest.raises(ValueError, match="positive"):
            chop(tmp_file, chunk_size=0)

    def test_empty_file_raises(self, tmp_path: Path):
        empty = tmp_path / "empty.bin"
        empty.write_bytes(b"")
        with pytest.raises(ValueError, match="empty"):
            chop(empty, chunk_size=1024)

    def test_progress_callback_called(self, tmp_file: Path, tmp_path: Path):
        calls = []
        chop(
            tmp_file,
            chunk_size=1024,
            output_dir=tmp_path,
            progress_cb=lambda done, total: calls.append((done, total)),
            verify=False,
        )
        assert len(calls) == 10
        assert calls[-1] == (10240, 10240)

    def test_default_output_dir_is_source_parent(self, tmp_file: Path):
        parts = chop(tmp_file, chunk_size=5000, verify=False)
        for p in parts:
            assert p.parent == tmp_file.parent
        # Cleanup
        for p in parts:
            p.unlink()


# ---------------------------------------------------------------------------
# join
# ---------------------------------------------------------------------------


class TestJoin:
    def test_round_trip(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=True)
        output = tmp_path / "reassembled.bin"
        result = join(parts, output=output, verify=True)
        assert result == output
        assert result.read_bytes() == tmp_file.read_bytes()

    def test_join_infers_output_name(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=2000, output_dir=tmp_path, verify=False)
        result = join(parts, verify=False)
        assert result.name == "sample.bin"
        result.unlink()

    def test_missing_part_raises(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=False)
        parts[3].unlink()  # remove part 4
        with pytest.raises(FileNotFoundError, match="not found"):
            join(parts, output=tmp_path / "out.bin", verify=False)

    def test_empty_parts_raises(self):
        with pytest.raises(ValueError, match="No part files"):
            join([])

    def test_checksum_mismatch_raises(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=True)
        # Corrupt the first part
        data = parts[0].read_bytes()
        parts[0].write_bytes(bytes([b ^ 0xFF for b in data]))
        with pytest.raises(ValueError, match="Checksum mismatch"):
            join(parts, output=tmp_path / "bad.bin", verify=True)

    def test_progress_callback_called(self, tmp_file: Path, tmp_path: Path):
        parts = chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=False)
        calls = []
        join(
            parts,
            output=tmp_path / "out.bin",
            progress_cb=lambda done, total: calls.append(done),
            verify=False,
        )
        assert calls[-1] == 10240


# ---------------------------------------------------------------------------
# find_parts
# ---------------------------------------------------------------------------


class TestFindParts:
    def test_finds_parts_in_order(self, tmp_file: Path, tmp_path: Path):
        chop(tmp_file, chunk_size=1024, output_dir=tmp_path, verify=False)
        parts = find_parts(tmp_path, "sample.bin")
        assert len(parts) == 10
        assert parts[0].name == "sample.bin.part0001"
        assert parts[-1].name == "sample.bin.part0010"

    def test_no_parts_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="No part files"):
            find_parts(tmp_path, "nonexistent.bin")


# ---------------------------------------------------------------------------
# sha256_of_file
# ---------------------------------------------------------------------------


class TestSha256OfFile:
    def test_known_digest(self, tmp_path: Path):
        import hashlib

        content = b"hello world"
        p = tmp_path / "hello.txt"
        p.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert sha256_of_file(p) == expected

    def test_consistent(self, tmp_file: Path):
        assert sha256_of_file(tmp_file) == sha256_of_file(tmp_file)


# ---------------------------------------------------------------------------
# CLI — chop command
# ---------------------------------------------------------------------------


class TestCliChop:
    def test_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "file_chopper" in captured.out
        assert "chop" in captured.out
        assert "join" in captured.out

    def test_chop_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["chop", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--size" in captured.out

    def test_chop_creates_parts(self, tmp_file: Path, tmp_path: Path):
        rc = main(["chop", str(tmp_file), "--size", "1K", "--output-dir", str(tmp_path), "--quiet"])
        assert rc == 0
        assert len(list(tmp_path.glob("*.part*"))) == 10

    def test_chop_dry_run_no_files(self, tmp_file: Path, tmp_path: Path):
        rc = main(["chop", str(tmp_file), "--size", "1K", "--output-dir", str(tmp_path), "--dry-run"])
        assert rc == 0
        assert list(tmp_path.glob("*.part*")) == []

    def test_chop_missing_file_returns_1(self, tmp_path: Path):
        rc = main(["chop", str(tmp_path / "ghost.bin"), "--size", "1MB"])
        assert rc == 1

    def test_chop_invalid_size_returns_1(self, tmp_file: Path):
        rc = main(["chop", str(tmp_file), "--size", "badsize"])
        assert rc == 1


# ---------------------------------------------------------------------------
# CLI — join command
# ---------------------------------------------------------------------------


class TestCliJoin:
    def test_join_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["join", "--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "--output" in captured.out

    def test_join_round_trip(self, tmp_file: Path, tmp_path: Path):
        main(["chop", str(tmp_file), "--size", "1K", "--output-dir", str(tmp_path), "--quiet"])
        first_part = tmp_path / "sample.bin.part0001"
        out = tmp_path / "result.bin"
        rc = main(["join", str(first_part), "--output", str(out), "--quiet"])
        assert rc == 0
        assert out.read_bytes() == tmp_file.read_bytes()

    def test_join_from_directory(self, tmp_file: Path, tmp_path: Path):
        main(["chop", str(tmp_file), "--size", "1K", "--output-dir", str(tmp_path), "--quiet"])
        out = tmp_path / "result.bin"
        rc = main(["join", str(tmp_path), "--base", "sample.bin", "--output", str(out), "--quiet"])
        assert rc == 0
        assert out.exists()

    def test_join_directory_without_base_returns_1(self, tmp_path: Path):
        rc = main(["join", str(tmp_path)])
        assert rc == 1

    def test_join_missing_part_returns_nonzero(self, tmp_file: Path, tmp_path: Path):
        main(["chop", str(tmp_file), "--size", "1K", "--output-dir", str(tmp_path), "--quiet"])
        (tmp_path / "sample.bin.part0005").unlink()
        first_part = tmp_path / "sample.bin.part0001"
        # Auto-discovery skips the missing part → checksum mismatch → rc=2
        rc = main(["join", str(first_part), "--quiet"])
        assert rc != 0

    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        assert "1.0.0" in capsys.readouterr().out
