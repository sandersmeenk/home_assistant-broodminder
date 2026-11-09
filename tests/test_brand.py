"""Tests for the brand images Home Assistant shows for the integration."""


from pathlib import Path
import struct

import pytest

BRAND_DIR = Path(__file__).parent.parent / "custom_components" / "broodminder" / "brand"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_size(path: Path) -> tuple[int, int]:
    """Return the width and height from a PNG's IHDR chunk."""
    header = path.read_bytes()[:24]
    assert header[:8] == PNG_SIGNATURE, f"{path.name} is not a PNG"
    assert header[12:16] == b"IHDR", f"{path.name} has no IHDR chunk first"
    return struct.unpack(">II", header[16:24])


@pytest.mark.parametrize(
    ("name", "size"),
    [
        ("icon.png", 256),
        ("icon@2x.png", 512),
    ],
)
def test_GIVEN_brand_folder_WHEN_reading_icon_THEN_square_png_of_expected_size(
    name: str, size: int
) -> None:
    """The brand folder has the icon as a square PNG of the size Home Assistant expects."""
    assert _png_size(BRAND_DIR / name) == (size, size)
