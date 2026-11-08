"""Tests for scripts/bump_latest.py."""

from typing import Any

import pytest

from scripts.bump_latest import (
    LATEST,
    BumpError,
    homeassistant_pin,
    integration_requirements,
    python_range,
    render,
)

# Manifests of Home Assistant integrations, by domain, as the core repository has them
MANIFESTS: dict[str, dict[str, Any]] = {
    "bluetooth_adapters": {
        "dependencies": ["bluetooth"],
        "after_dependencies": ["esphome"],
    },
    "bluetooth": {
        "requirements": ["bleak==3.0.2", "habluetooth==7.1.2"],
        "dependencies": ["usb"],
    },
    "usb": {"requirements": ["aiousbwatcher==1.1.2"], "dependencies": ["websocket_api"]},
    "websocket_api": {"dependencies": ["http"]},
    "http": {},
    "esphome": {"requirements": ["aioesphomeapi==46.6.0"], "dependencies": ["bluetooth"]},
}


def test_GIVEN_plugin_requirements_WHEN_homeassistant_pin_THEN_its_version_is_returned() -> None:
    """Verifies the Home Assistant version is taken from the plugin's pinned requirement."""
    requires_dist = ["pytest==9.0.0", "homeassistant==2026.10.4", "homeassistant-stubs; extra"]
    assert homeassistant_pin(requires_dist) == "2026.10.4"


def test_GIVEN_no_homeassistant_pin_WHEN_homeassistant_pin_THEN_error_is_raised() -> None:
    """Verifies a plugin release without a pinned Home Assistant is refused."""
    with pytest.raises(BumpError, match="doesn't pin homeassistant"):
        homeassistant_pin(["homeassistant>=2026.1", "pytest==9.0.0"])


@pytest.mark.parametrize(
    ("requires_python", "expected"),
    [(">=3.14.2", ">=3.14.2,<3.15"), (">= 3.13", ">=3.13,<3.14")],
    ids=["with_patch", "without_patch"],
)
def test_GIVEN_minimum_python_WHEN_python_range_THEN_range_stays_within_minor_version(
    requires_python: str, expected: str
) -> None:
    """Verifies the environment's Python stays in the minor version Home Assistant requires."""
    assert python_range(requires_python) == expected


def test_GIVEN_unexpected_python_requirement_WHEN_python_range_THEN_error_is_raised() -> None:
    """Verifies a Python requirement that isn't a plain minimum is refused."""
    with pytest.raises(BumpError, match="Python version"):
        python_range(">=3.14,<3.16")


def test_GIVEN_dependencies_WHEN_integration_requirements_THEN_dependencies_followed() -> None:
    """Verifies dependencies are followed, after_dependencies aren't, and each is read once."""
    loaded: list[str] = []

    def load_manifest(domain: str) -> dict[str, Any]:
        loaded.append(domain)
        return MANIFESTS[domain]

    requirements = integration_requirements(["bluetooth_adapters", "bluetooth"], load_manifest)

    assert requirements == ["aiousbwatcher==1.1.2", "bleak==3.0.2", "habluetooth==7.1.2"]
    assert sorted(loaded) == ["bluetooth", "bluetooth_adapters", "http", "usb", "websocket_api"]


def test_GIVEN_versions_WHEN_render_THEN_setup_can_read_python_and_pins_match() -> None:
    """Verifies the file starts with the Python line scripts/setup reads and pins both."""
    text = render(
        "0.13.375",
        "2026.10.4",
        ">=3.14.2,<3.15",
        ["bluetooth_adapters", "bluetooth"],
        ["aiousbwatcher==1.1.2", "bleak==3.0.2"],
    )
    lines = text.splitlines()

    assert lines[0] == "# python: >=3.14.2,<3.15"
    assert "-r dev.txt" in lines
    assert "homeassistant==2026.10.4" in lines
    assert "pytest-homeassistant-custom-component==0.13.375" in lines
    assert "# load: bluetooth, bluetooth_adapters and their dependencies" in lines
    assert lines[-2:] == ["aiousbwatcher==1.1.2", "bleak==3.0.2"]


def test_GIVEN_repository_latest_requirements_WHEN_read_THEN_written_by_bump_latest() -> None:
    """Verifies requirements/latest.txt has the layout bump_latest.py writes."""
    lines = LATEST.read_text(encoding="utf-8").splitlines()

    assert lines[0].startswith("# python: >=3.")
    assert any(line.startswith("homeassistant==") for line in lines)
    assert any(line.startswith("pytest-homeassistant-custom-component==") for line in lines)
