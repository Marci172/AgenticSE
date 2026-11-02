"""Check every line of a requirements.txt against PyPI before running pip install.

Always checks compatibility against Python 3.11, regardless of the interpreter
running this script.

Usage: python check_requirements.py [path/to/requirements.txt]
"""
import json
import sys
import urllib.error
import urllib.request

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

TARGET_PYTHON = "3.11"
# Every 3.11.x patch release, so bounds like ">=3.11.4" or "<3.11.2" are handled.
TARGET_VERSIONS = [Version(f"{TARGET_PYTHON}.{patch}") for patch in range(0, 20)]
PYPI_URL = "https://pypi.org/pypi/{}/json"


def fetch_project(name):
    """Return the PyPI JSON for a project, or None if it does not exist."""
    try:
        with urllib.request.urlopen(PYPI_URL.format(name), timeout=15) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise


def release_requires_python(files):
    """requires_python of a release, taken from its uploaded files ('' if undeclared)."""
    for f in files:
        if f.get("requires_python"):
            return f["requires_python"]
    return ""


def supports_target(requires_python):
    """True if requires_python (lower AND upper bound) allows some Python 3.11.x."""
    if not requires_python:
        return True  # no restriction declared
    try:
        spec = SpecifierSet(requires_python)
    except InvalidSpecifier:
        return True  # malformed metadata; pip ignores it too
    return any(spec.contains(v) for v in TARGET_VERSIONS)


def min_python(requires_python):
    """Lowest Python version a requires_python string asks for (its lower bound)."""
    try:
        spec = SpecifierSet(requires_python)
    except InvalidSpecifier:
        return None
    bounds = []
    for s in spec:
        if s.operator in (">=", ">", "~=", "==") and "*" not in s.version:
            try:
                bounds.append(Version(s.version))
            except InvalidVersion:
                pass
    return max(bounds) if bounds else None


def check_requirement(req, project):
    """Return (status, version, requires_python) for one parsed requirement.

    status is one of "missing", "incompatible", "ok".
    """
    releases, yanked = {}, {}
    for ver_str, files in project["releases"].items():
        if not files:
            continue  # version registered but nothing uploaded
        try:
            v = Version(ver_str)
        except InvalidVersion:
            continue
        target = yanked if all(f.get("yanked") for f in files) else releases
        target[v] = files

    # Releases that satisfy the line's specifier (e.g. ==1.2.3 or >=2.0).
    # SpecifierSet.filter applies pip's pre-release rules for us.
    matching = sorted(req.specifier.filter(releases), reverse=True)
    if not matching:
        # PEP 592: pip still installs a yanked release if it is pinned exactly.
        specs = list(req.specifier)
        if len(specs) == 1 and specs[0].operator in ("==", "==="):
            pinned = sorted(req.specifier.filter(yanked), reverse=True)
            if pinned:
                v = pinned[0]
                rp = release_requires_python(yanked[v])
                return ("ok" if supports_target(rp) else "incompatible"), v, rp
        return "missing", None, None

    # Like pip: take the newest matching release that supports Python 3.11.
    for v in matching:
        rp = release_requires_python(releases[v])
        if supports_target(rp):
            return "ok", v, rp
    newest = matching[0]
    return "incompatible", newest, release_requires_python(releases[newest])


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "requirements.txt"
    with open(path, encoding="utf-8") as fh:
        raw_lines = fh.read().splitlines()

    lines = []
    for raw in raw_lines:
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        lines.append(line)

    not_found, incompatible, skipped, unparseable = [], [], [], []
    highest = None  # (min_python, name, version, requires_python)
    marker_env = {"python_version": TARGET_PYTHON, "python_full_version": f"{TARGET_PYTHON}.0"}

    for line in lines:
        if line.startswith("-"):
            skipped.append(f"{line}  (pip option, not checked)")
            continue
        try:
            req = Requirement(line)
        except InvalidRequirement:
            unparseable.append(line)
            continue
        if req.marker and not req.marker.evaluate(marker_env):
            skipped.append(f"{line}  (environment marker does not apply here)")
            continue

        project = fetch_project(req.name)
        if project is None:
            not_found.append(f"{line}  (package does not exist)")
            continue

        status, version, requires_python = check_requirement(req, project)
        if status == "missing":
            not_found.append(f"{line}  (no release matches {req.specifier or 'any version'})")
            continue
        if status == "incompatible":
            incompatible.append(f"{req.name}=={version}  (requires_python: {requires_python})")

        # Every release that exists counts here, compatible with 3.11 or not.
        if requires_python:
            lower = min_python(requires_python)
            if lower is not None and (highest is None or lower > highest[0]):
                highest = (lower, req.name, version, requires_python)

    print(f"Dependencies checked: {len(lines)}")
    print(f"\nNot found on PyPI ({len(not_found)}):")
    for item in not_found:
        print(f"  {item}")
    print(f"\nIncompatible with Python {TARGET_PYTHON} ({len(incompatible)}):")
    for item in incompatible:
        print(f"  {item}")
    if unparseable:
        print(f"\nUnparseable lines ({len(unparseable)}):")
        for item in unparseable:
            print(f"  {item}")
    if skipped:
        print(f"\nSkipped ({len(skipped)}):")
        for item in skipped:
            print(f"  {item}")
    print("\nHighest Python requirement:")
    if highest:
        lower, name, version, _ = highest
        print(f"  {name} == {version} (>= {lower})")
    else:
        print("  none (no resolved release declares requires_python)")

    return 1 if (not_found or incompatible or unparseable) else 0


if __name__ == "__main__":
    sys.exit(main())
