import json
from pathlib import Path


def test_manifest_is_valid_json_and_keys_exist():
    manifest_path = Path("custom_components/broodminder/manifest.json")
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    for key in ("domain", "name", "version", "bluetooth", "min_homeassistant_version"):
        assert key in data
    assert data["domain"] == "broodminder"
    assert any(entry.get("manufacturer_id") == 653 for entry in data["bluetooth"])
