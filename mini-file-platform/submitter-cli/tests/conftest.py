import sys
from pathlib import Path

# Make 'shared' importable from the project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
