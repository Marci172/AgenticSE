# AgenticSE

## check_requirements.py

Checks every line of a `requirements.txt` against PyPI **before** you run
`pip install`. It catches the typical mistakes of AI-written requirement files:
packages that don't exist, pinned versions that were never released, and
releases that don't support Python 3.11.

The check always targets **Python 3.11**, no matter which Python runs the script.

### Requirements

- Python 3.8+
- [`packaging`](https://pypi.org/project/packaging/) (`pip install packaging`)
- Internet access (uses the PyPI JSON API, `https://pypi.org/pypi/<name>/json`)

### Usage

```bash
python check_requirements.py                       # checks ./requirements.txt
python check_requirements.py path/to/requirements.txt
```

### Example

```
$ python check_requirements.py requirements.txt
Dependencies checked: 5

Not found on PyPI (1):
  langchain-pdf-agent==0.1.0  (package does not exist)

Incompatible with Python 3.11 (2):
  django==6.0  (requires_python: >=3.12)
  numpy==1.21.6  (requires_python: >=3.7,<3.11)

Highest Python requirement:
  django == 6.0 (>= 3.12)
```

### What is reported

| Section | Meaning |
|---|---|
| Dependencies checked | Number of non-empty, non-comment lines in the file |
| Not found on PyPI | The package does not exist, or no release matches the pinned version |
| Incompatible with Python 3.11 | The release exists, but its `requires_python` (lower and upper bound) excludes 3.11 |
| Highest Python requirement | Among existing releases that declare `requires_python`, the one with the highest minimum Python version |

Unpinned lines (e.g. `pandas>=2.0`) are resolved like pip does: the newest matching
release that supports Python 3.11. Pip options (`-e .`, `-r ...`) and lines whose
environment marker does not apply are listed as skipped.

The exit code is `1` if anything was not found, incompatible or unparseable, so the
check can gate an install:

```bash
python check_requirements.py && pip install -r requirements.txt
```

Note: the check relies on each package's published `requires_python` metadata.
