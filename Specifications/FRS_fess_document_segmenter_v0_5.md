# Functional Requirements Specification (S.M.A.R.T.)
**Project:** Fess Document Segmenter (Python)  
**Version:** 0.5 (Out-of-scope format policy clarified)  
**Date:** 2026-02-21  
**Status:** Draft (ready for review)

## 1. Purpose
Build a cross-platform Python CLI tool that splits large source documents into multiple smaller child documents and prepares an output folder structure suitable for a Fess filesystem crawl, such that keyword search works across the entire logical content of each original (parent) document.

## 2. Hard Constraints
1) Installer MUST be a single Python script (`install.py`).  
2) No installation of non-Python external programs is allowed.  
3) All conversion and extraction must use Python libraries only.

## 3. Supported Formats (v1)

### 3.1 Must-support (pure Python pipeline)
- `.pdf`
- `.txt`, `.csv`, `.md`
- `.html`, `.htm`
- `.docx`, `.pptx`, `.xlsx`
- `.odt`, `.odp`, `.ods`
- `.rtf` (best-effort)

### 3.2 Explicitly out-of-scope (v1)
- `.doc`, `.ppt`, `.xls` (legacy binary Office)

## 4. Split Decision Rule

Splitting is required if either:
- file size > `max_child_bytes`, OR
- extracted text chars > `max_child_text_chars`.

## 5. Policy for Out-of-Scope Formats (Final Rule)

This replaces previous ambiguity.

### Case A — Split NOT required
If a document is out-of-scope (e.g., `.doc`) AND splitting is NOT required:

- The tool SHALL copy the file unchanged to the mirrored output location.
- No warning is required.
- The file is treated as successfully processed.

### Case B — Split required
If a document is out-of-scope AND splitting IS required:

- The tool SHALL mark the file as `error`.
- No output file(s) are produced for that parent.
- Processing continues unless `--fail-fast=true`.
- Error message MUST include:
  - file path
  - reason (format not supported for conversion in v1)
  - remediation hint (convert manually to PDF or use newer format like .docx)

## 6. Fully Searchable Definition (D4)

A parent document is considered fully searchable when:

- It is copied unchanged (no split required), OR
- It is successfully split and every child satisfies:
  `child_text_chars ≤ max_child_text_chars`.

## 7. Installer Requirement (Python-only)

The project SHALL include `install.py` that:

1) Creates `.venv`  
2) Installs Python dependencies into that venv  
3) Validates Python version (>= 3.11)  
4) Prints the exact command to run the CLI  

No OS-specific shell or PowerShell installers are allowed.

## 8. Exit Codes

- 0: success (no errors)
- 1: completed with errors (at least one file failed)
- 2: configuration/argument error
- 3: missing Python dependency error
