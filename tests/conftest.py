"""Put the skill's scripts dir on sys.path so tests can import the modules.

The scripts live under a hyphenated directory (not a Python package), so we add
the directory itself and import by module name.
"""

import sys
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parent.parent
    / "skills"
    / "analyze-chess-games"
    / "scripts"
)
sys.path.insert(0, str(SCRIPTS))
