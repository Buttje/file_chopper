# Acceptance Test Specification
**Project:** Fess Document Segmenter (Python)  
**Version:** 0.5 (Out-of-scope policy clarified)  
**Date:** 2026-02-21

## 1. Test Environment Matrix
- Windows 10
- Windows 11
- Linux (Ubuntu 22.04+)
Python >= 3.11
No external programs allowed.

## 2. Test Data
Include:
- Valid large PDF
- Valid DOCX
- Legacy `.doc` (binary)
- Small `.doc` within limits
- Large `.doc` exceeding limits

## 3. Test Cases

### AT-1 Out-of-scope format, no split required
Given a small `sample.doc` within both limits  
When the tool runs  
Then the file is copied unchanged  
And no error is raised  
And exit code remains 0.

### AT-2 Out-of-scope format, split required
Given a large `sample.doc` exceeding `max_child_text_chars`  
When the tool runs  
Then the file is marked as error  
And no output file is created  
And exit code is non-zero  
And the error message explains the format limitation and remediation.

### AT-3 Must-support format still processed normally
Given a large `.docx`  
When the tool runs  
Then it is converted via pure-Python pipeline  
And split into index-safe child PDFs.

