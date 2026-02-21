# file_chopper

**Split large files into smaller pieces — and rejoin them.**

`file_chopper` is a cross-platform command-line tool that lets you chop any
file into chunks of a specified size and later reassemble them with a single
command.  It works on **Windows 10**, **Windows 11** and **Linux**.

---

## Installation

### Prerequisites

* Python 3.8 or newer ([download](https://www.python.org/downloads/))

### One-command setup

```bash
# Windows
python install.py

# Linux / macOS
python3 install.py
```

The installer:

1. Creates a virtual environment in `.venv/`
2. Installs all runtime dependencies
3. Creates a platform-specific launcher (`run_file_chopper.bat` on Windows,
   `run_file_chopper.sh` on Linux)

---

## Quick Start

```bash
# Split a large file into 700 MB pieces
file_chopper chop big_backup.tar --size 700MB

# Reassemble from the first part (all sibling parts are found automatically)
file_chopper join big_backup.tar.part0001

# Preview without writing anything
file_chopper chop big_backup.tar --size 700MB --dry-run
```

---

## Usage

### `chop` — split a file

```
file_chopper chop FILE --size SIZE [--output-dir DIR] [--no-verify] [--dry-run] [--quiet]
```

| Option | Description |
|--------|-------------|
| `FILE` | Path to the file to split |
| `--size SIZE` | Maximum chunk size, e.g. `100MB`, `700K`, `2G` |
| `--output-dir DIR` | Where to write the chunks (default: same directory as `FILE`) |
| `--no-verify` | Skip writing the SHA-256 checksum file |
| `--dry-run` | Show what would be created without writing anything |
| `--quiet` | Suppress progress output |

### `join` — reassemble a file

```
file_chopper join PART [PART ...] [--output FILE] [--base NAME] [--no-verify] [--quiet]
```

| Option | Description |
|--------|-------------|
| `PART` | A `.partNNNN` file, a directory (with `--base`), or explicit list of parts |
| `--output FILE` | Path for the output file (inferred from part name when omitted) |
| `--base NAME` | Base file name when `PART` is a directory |
| `--no-verify` | Skip SHA-256 integrity check |
| `--quiet` | Suppress progress output |

### Size units

| Unit | Size |
|------|------|
| `B` | bytes |
| `K` / `KB` | kibibytes (1 024 B) |
| `M` / `MB` | mebibytes (1 024 KB) |
| `G` / `GB` | gibibytes (1 024 MB) |
| `T` / `TB` | tebibytes (1 024 GB) |

---

## Development

```bash
# Install with development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src tests
```

---

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | User error (bad arguments, file not found, …) |
| `2` | Integrity error (SHA-256 checksum mismatch) |

---

## License

See [LICENSE](LICENSE).
