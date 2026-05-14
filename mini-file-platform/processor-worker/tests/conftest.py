import sys
from pathlib import Path

# Add mini-file-platform root so `shared` is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
