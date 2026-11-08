#!/usr/bin/env python
"""Write requirements/latest.txt for the newest Home Assistant the test plugin supports.

Each pytest-homeassistant-custom-component release is built against one Home Assistant release.
This takes the newest plugin release, the Home Assistant version it pins and the Python version
that one needs. It also pins the requirements of the Home Assistant integrations ours depends
on, such as bluetooth: the tests load them, but the plugin doesn't install them.
"""

from collections.abc import Callable
import json
from pathlib import Path
import re
import sys
from typing import Any
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "broodminder" / "manifest.json"
LATEST = ROOT / "requirements" / "latest.txt"

PLUGIN = "pytest-homeassistant-custom-component"

HOMEASSISTANT_PIN = re.compile(r"^homeassistant\s*==\s*(?P<version>[^\s;]+)")
MINIMUM_PYTHON = re.compile(r"^>=\s*(?P<major>\d+)\.(?P<minor>\d+)(?P<patch>\.\d+)?$")


class BumpError(Exception):
    """Raised when the plugin or Home Assistant metadata isn't as expected."""


def homeassistant_pin(requires_dist: list[str]) -> str:
    """Return the Home Assistant version a plugin release requires."""
    for requirement in requires_dist:
        if match := HOMEASSISTANT_PIN.match(requirement):
            return match["version"]
    msg = f"{PLUGIN} doesn't pin homeassistant"
    raise BumpError(msg)


def python_range(requires_python: str) -> str:
    """Return the Python versions to create the environment with, e.g. >=3.14.2,<3.15.

    Home Assistant only gives a minimum; the range stays within that minor version.
    """
    match = MINIMUM_PYTHON.match(requires_python.strip())
    if match is None:
        msg = f"Can't read Home Assistant's Python version: {requires_python}"
        raise BumpError(msg)
    major, minor = int(match["major"]), int(match["minor"])
    return f"{requires_python.strip().replace(' ', '')},<{major}.{minor + 1}"


def integration_requirements(
    domains: list[str], load_manifest: Callable[[str], dict[str, Any]]
) -> list[str]:
    """Return the requirements of these Home Assistant integrations and their dependencies.

    after_dependencies are only loaded when configured, so they aren't followed.
    """
    requirements: set[str] = set()
    seen: set[str] = set()
    todo = list(domains)
    while todo:
        domain = todo.pop()
        if domain in seen:
            continue
        seen.add(domain)
        manifest = load_manifest(domain)
        requirements.update(manifest.get("requirements", []))
        todo.extend(manifest.get("dependencies", []))
    return sorted(requirements, key=str.lower)


def render(
    plugin_version: str, ha_version: str, python: str, domains: list[str], requirements: list[str]
) -> str:
    """Return the contents of requirements/latest.txt."""
    lines = [
        f"# python: {python}",
        "#",
        "# The newest Home Assistant the test plugin supports. Written by",
        "# scripts/bump_latest.py: don't edit. The line above is the Python version",
        "# scripts/setup creates .venv-latest with.",
        "-r dev.txt",
        f"homeassistant=={ha_version}",
        "# Must match homeassistant: each plugin release is built against one Home Assistant",
        "# release",
        f"{PLUGIN}=={plugin_version}",
        "# Requirements of the Home Assistant integrations ours depends on, which the tests",
        f"# load: {', '.join(sorted(domains))} and their dependencies",
        *requirements,
    ]
    return "\n".join(lines) + "\n"


def _pypi(path: str) -> Any:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{path}/json", timeout=30) as response:
        return json.load(response)


def _core_manifest(ha_version: str, domain: str) -> dict[str, Any]:
    with urllib.request.urlopen(
        f"https://raw.githubusercontent.com/home-assistant/core/{ha_version}/homeassistant/"
        f"components/{domain}/manifest.json",
        timeout=30,
    ) as response:
        return json.load(response)


def main() -> int:
    """Write requirements/latest.txt and print what changed."""
    try:
        plugin = _pypi(PLUGIN)["info"]
        ha_version = homeassistant_pin(plugin["requires_dist"] or [])
        homeassistant = _pypi(f"homeassistant/{ha_version}")
        python = python_range(homeassistant["info"]["requires_python"])
    except BumpError as err:
        sys.stderr.write(f"{err}\n")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    domains = manifest.get("dependencies", []) + manifest.get("after_dependencies", [])
    requirements = integration_requirements(
        domains, lambda domain: _core_manifest(ha_version, domain)
    )

    old = LATEST.read_text(encoding="utf-8") if LATEST.exists() else ""
    new = render(plugin["version"], ha_version, python, domains, requirements)
    if new == old:
        print(f"Already at Home Assistant {ha_version} ({PLUGIN} {plugin['version']})")
    else:
        LATEST.write_text(new, encoding="utf-8")
        print(f"Updated to Home Assistant {ha_version} ({PLUGIN} {plugin['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
