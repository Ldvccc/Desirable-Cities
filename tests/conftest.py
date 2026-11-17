import sys
from pathlib import Path

# make `src/` importable in tests (python -m pytest from the project root)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))