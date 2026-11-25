"""Aide commune des tests du lot 0.1 : rend scripts/ importable."""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
SCRIPTS = RACINE / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
