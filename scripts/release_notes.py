#!/usr/bin/env python
"""Print the CHANGELOG.md section of a version, for use as GitHub release notes."""

import argparse
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"

# Version headings, e.g. "## [0.3.0] - 2025-11-20"
VERSION_HEADING = re.compile(r"^## \[(?P<version>[^\]]+)\] - (?P<date>.+)$")
# "[0.3.0]: https://..." link definitions at the bottom of the changelog
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]: ")


class ReleaseNotesError(Exception):
    """Raised when a version has no releasable section in the changelog."""


def release_notes(changelog: str, version: str) -> str:
    """Return the body of the section of a released version in the changelog."""
    body: list[str] | None = None
    for line in changelog.splitlines():
        heading = VERSION_HEADING.match(line)
        if body is None:
            if heading and heading["version"] == version:
                if heading["date"].strip().lower() == "unreleased":
                    msg = f"Version {version} is marked Unreleased in the changelog"
                    raise ReleaseNotesError(msg)
                body = []
        elif heading or line.startswith("## ") or LINK_DEFINITION.match(line):
            break
        else:
            body.append(line)

    if body is None:
        msg = f"Version {version} not found in the changelog"
        raise ReleaseNotesError(msg)
    notes = "\n".join(body).strip()
    if not notes:
        msg = f"Version {version} has no changes in the changelog"
        raise ReleaseNotesError(msg)
    return notes + "\n"


def main() -> int:
    """Print the release notes of the version given on the command line."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="version as in the changelog heading, e.g. 0.3.0")
    args = parser.parse_args()
    try:
        sys.stdout.write(release_notes(CHANGELOG.read_text(encoding="utf-8"), args.version))
    except ReleaseNotesError as err:
        sys.stderr.write(f"{err}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
