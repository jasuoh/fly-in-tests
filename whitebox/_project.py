"""Locate the project under test and make its ``src`` package importable.

The project root is ``$FLY_IN_PROJECT`` or, by default, the directory that
contains this repository (layout ``project/fly-in-tests``).
"""

import os
import sys
from pathlib import Path

TESTER = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("FLY_IN_PROJECT") or TESTER.parent).resolve()
MAPS = TESTER / "maps" / "provided"

if not (ROOT / "src").is_dir():
    raise ImportError(f"no project with a src/ directory at {ROOT}; "
                      "set FLY_IN_PROJECT")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
