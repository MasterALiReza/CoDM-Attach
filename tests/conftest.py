# Ensure project root is on sys.path so `import core`, `import utils` work in tests
import sys
import os
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
ROOT = THIS_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
