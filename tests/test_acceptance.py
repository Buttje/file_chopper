"""
Acceptance Tests for the Fess Document Segmenter.

Based on: ATS_fess_document_segmenter_v0_5.md

AT-1  Out-of-scope format (.doc), no split required  → copy unchanged, exit 0
AT-2  Out-of-scope format (.doc), split required     → error, exit non-zero
AT-3  Must-support format (.docx), large document    → split into child files, exit 0
"""

from __future__ import annotations

from pathlib import Path

from file_chopper.main import main
from file_chopper.segmenter import SegmentStatus, segment_document

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_doc_file(path: Path, size_bytes: int) -> Path:
    """Create a fake .doc file of *size_bytes* bytes."""
    path.write_bytes(b"\xd0\xcf\x11\xe0" + b"X" * (size_bytes - 4))
    return path


def _make_docx_file(path: Path, num_paragraphs: int, chars_per_para: int) -> Path:
    """Create a real .docx file with *num_paragraphs* paragraphs."""
    import docx  # python-docx

    doc = docx.Document()
    for _ in range(num_paragraphs):
        doc.add_paragraph("A" * chars_per_para)
    doc.save(str(path))
    return path


# ---------------------------------------------------------------------------
# AT-1: Out-of-scope format, NO split required
# ---------------------------------------------------------------------------


class TestAT1OutOfScopeNoSplit:
    """AT-1 — small .doc within both limits is copied unchanged; exit 0."""

    def test_file_is_copied_unchanged(self, tmp_path: Path):
        # Given a small sample.doc within both limits
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=500)
        output_dir = tmp_path / "output"

        # When the tool runs
        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        # Then the file is copied unchanged
        assert result.status == SegmentStatus.OK
        assert len(result.children) == 1
        dest = result.children[0]
        assert dest.name == "sample.doc"
        assert dest.read_bytes() == doc_file.read_bytes()

    def test_no_error_is_raised(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=500)
        output_dir = tmp_path / "output"

        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        assert result.status != SegmentStatus.ERROR
        assert result.error_msg == ""

    def test_cli_exit_code_is_0(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=500)
        output_dir = tmp_path / "output"

        rc = main(
            [
                "segment",
                str(doc_file),
                "--output-dir",
                str(output_dir),
                "--max-size",
                "10KB",
                "--max-chars",
                "50000",
                "--quiet",
            ]
        )

        # Then exit code remains 0
        assert rc == 0


# ---------------------------------------------------------------------------
# AT-2: Out-of-scope format, split required
# ---------------------------------------------------------------------------


class TestAT2OutOfScopeSplitRequired:
    """AT-2 — large .doc exceeding max_child_bytes is marked as error."""

    def test_result_is_error(self, tmp_path: Path):
        # Given a large sample.doc exceeding max_child_bytes
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=20_000)
        output_dir = tmp_path / "output"

        # When the tool runs
        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        # Then the file is marked as error
        assert result.status == SegmentStatus.ERROR

    def test_no_output_file_is_created(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=20_000)
        output_dir = tmp_path / "output"

        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        assert result.children == []
        # No file written in output_dir for this parent
        assert not list(output_dir.glob("sample.doc*"))

    def test_error_message_includes_file_path(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=20_000)
        output_dir = tmp_path / "output"

        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        assert str(doc_file) in result.error_msg

    def test_error_message_includes_reason(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=20_000)
        output_dir = tmp_path / "output"

        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        assert "not supported" in result.error_msg.lower()

    def test_error_message_includes_remediation(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=20_000)
        output_dir = tmp_path / "output"

        result = segment_document(
            source=doc_file,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
        )

        assert "docx" in result.error_msg.lower() or "pdf" in result.error_msg.lower()

    def test_cli_exit_code_is_nonzero(self, tmp_path: Path):
        doc_file = _make_doc_file(tmp_path / "sample.doc", size_bytes=20_000)
        output_dir = tmp_path / "output"

        rc = main(
            [
                "segment",
                str(doc_file),
                "--output-dir",
                str(output_dir),
                "--max-size",
                "10KB",
                "--max-chars",
                "50000",
                "--quiet",
            ]
        )

        # Then exit code is non-zero
        assert rc != 0

    def test_processing_continues_without_fail_fast(self, tmp_path: Path):
        """Without --fail-fast, processing should continue after an error."""
        large_doc = _make_doc_file(tmp_path / "large.doc", size_bytes=20_000)
        small_txt = tmp_path / "small.txt"
        small_txt.write_text("Hello world", encoding="utf-8")
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        (input_dir / "large.doc").write_bytes(large_doc.read_bytes())
        (input_dir / "small.txt").write_bytes(small_txt.read_bytes())
        output_dir = tmp_path / "output"

        from file_chopper.segmenter import segment_folder

        results = segment_folder(
            input_dir=input_dir,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
            fail_fast=False,
        )

        # Both files processed: one error, one ok
        statuses = {r.source.name: r.status for r in results}
        assert statuses["large.doc"] == SegmentStatus.ERROR
        assert statuses["small.txt"] == SegmentStatus.OK

    def test_fail_fast_stops_after_first_error(self, tmp_path: Path):
        """With fail_fast=True, processing stops after the first error."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        _make_doc_file(input_dir / "aaa_large.doc", size_bytes=20_000)
        (input_dir / "zzz_small.txt").write_text("Hello", encoding="utf-8")
        output_dir = tmp_path / "output"

        from file_chopper.segmenter import segment_folder

        results = segment_folder(
            input_dir=input_dir,
            output_dir=output_dir,
            max_child_bytes=10_000,
            max_child_text_chars=50_000,
            fail_fast=True,
        )

        # Only the first (error) file was processed
        assert len(results) == 1
        assert results[0].status == SegmentStatus.ERROR


# ---------------------------------------------------------------------------
# AT-3: Must-support format (.docx), large document
# ---------------------------------------------------------------------------


class TestAT3MustSupportFormatProcessed:
    """AT-3 — large .docx is converted via pure-Python pipeline and split."""

    def test_docx_is_split_into_multiple_children(self, tmp_path: Path):
        # Given a large .docx file
        docx_file = _make_docx_file(
            tmp_path / "large.docx",
            num_paragraphs=20,
            chars_per_para=500,
        )
        output_dir = tmp_path / "output"

        # When the tool runs with small max_chars to force splitting
        result = segment_document(
            source=docx_file,
            output_dir=output_dir,
            max_child_bytes=100 * 1024 * 1024,  # large enough so size alone won't trigger
            max_child_text_chars=1_000,  # force split: 20 * 500 = 10000 chars
        )

        # Then it is successfully processed
        assert result.status == SegmentStatus.OK
        # And split into multiple child files
        assert len(result.children) > 1

    def test_all_children_respect_max_chars(self, tmp_path: Path):
        docx_file = _make_docx_file(
            tmp_path / "large.docx",
            num_paragraphs=20,
            chars_per_para=500,
        )
        output_dir = tmp_path / "output"
        max_chars = 1_000

        result = segment_document(
            source=docx_file,
            output_dir=output_dir,
            max_child_bytes=100 * 1024 * 1024,
            max_child_text_chars=max_chars,
        )

        assert result.status == SegmentStatus.OK
        for child in result.children:
            child_text = child.read_text(encoding="utf-8")
            assert len(child_text) <= max_chars

    def test_cli_exit_code_is_0(self, tmp_path: Path):
        docx_file = _make_docx_file(
            tmp_path / "large.docx",
            num_paragraphs=20,
            chars_per_para=500,
        )
        output_dir = tmp_path / "output"

        rc = main(
            [
                "segment",
                str(docx_file),
                "--output-dir",
                str(output_dir),
                "--max-size",
                "100MB",
                "--max-chars",
                "1000",
                "--quiet",
            ]
        )

        assert rc == 0

    def test_no_split_when_within_limits(self, tmp_path: Path):
        """Small .docx within limits is copied unchanged."""
        docx_file = _make_docx_file(
            tmp_path / "small.docx",
            num_paragraphs=2,
            chars_per_para=50,
        )
        output_dir = tmp_path / "output"

        result = segment_document(
            source=docx_file,
            output_dir=output_dir,
            max_child_bytes=10 * 1024 * 1024,
            max_child_text_chars=50_000,
        )

        assert result.status == SegmentStatus.OK
        assert len(result.children) == 1
        assert result.children[0].suffix == ".docx"
