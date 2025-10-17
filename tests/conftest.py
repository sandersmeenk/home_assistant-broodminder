import sys
from pathlib import Path

# Ensure custom_components is importable during tests
ROOT = Path(__file__).resolve().parents[1]
CC = ROOT / "custom_components"
if str(CC) not in sys.path:
    sys.path.insert(0, str(CC))
