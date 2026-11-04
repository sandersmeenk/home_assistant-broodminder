"""Tests for scripts/release_notes.py."""

import pytest

from scripts.release_notes import CHANGELOG, ReleaseNotesError, release_notes

CHANGELOG_TEXT = """# Changelog

Intro text.

## [0.4.0] - Unreleased

### Added

- Something new.

## [0.3.0] - 2025-11-20

### Changed

- Something changed.

## [0.2.0] - 2025-11-19

First release.

[0.4.0]: https://example.com/compare/0.3.0...develop
[0.3.0]: https://example.com/compare/0.2.0...0.3.0
"""


def test_GIVEN_released_version_WHEN_release_notes_THEN_only_its_section_is_returned() -> None:
    """Verifies the notes stop at the next version heading."""
    assert release_notes(CHANGELOG_TEXT, "0.3.0") == "### Changed\n\n- Something changed.\n"


def test_GIVEN_last_version_WHEN_release_notes_THEN_link_definitions_are_excluded() -> None:
    """Verifies the link definitions at the bottom aren't part of the oldest version's notes."""
    assert release_notes(CHANGELOG_TEXT, "0.2.0") == "First release.\n"


def test_GIVEN_unreleased_version_WHEN_release_notes_THEN_error_is_raised() -> None:
    """Verifies a version still marked Unreleased can't be released."""
    with pytest.raises(ReleaseNotesError, match="Unreleased"):
        release_notes(CHANGELOG_TEXT, "0.4.0")


def test_GIVEN_unknown_version_WHEN_release_notes_THEN_error_is_raised() -> None:
    """Verifies a version missing from the changelog can't be released."""
    with pytest.raises(ReleaseNotesError, match="not found"):
        release_notes(CHANGELOG_TEXT, "9.9.9")


def test_GIVEN_empty_section_WHEN_release_notes_THEN_error_is_raised() -> None:
    """Verifies a version without changes can't be released."""
    with pytest.raises(ReleaseNotesError, match="no changes"):
        release_notes("## [1.0.0] - 2026-01-01\n\n## [0.9.0] - 2025-01-01\n", "1.0.0")


def test_GIVEN_repository_changelog_WHEN_release_notes_THEN_released_versions_have_notes() -> (
    None
):
    """Verifies the released versions in the repository changelog can be released."""
    changelog = CHANGELOG.read_text(encoding="utf-8")
    for version in ("0.2.0", "0.3.0"):
        assert release_notes(changelog, version)
