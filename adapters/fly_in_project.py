"""Headless command line for a Fly-In project that offers ``build_scheduler``.

The project's own entry point opens a Pygame window, which a black-box
tester cannot drive. This adapter runs the same steps as ``src/__main__.py``
(parse, plan, simulate) and prints the turn log, so the tester can check the
real logic of the project.

    python adapters/fly_in_project.py MAP

The project root is taken from ``$FLY_IN_PROJECT``; by default it is the
directory that contains this repository (the layout ``project/fly-in-tests``).
"""

import os
import sys
from pathlib import Path


def project_root() -> Path:
    """Return the root directory of the project under test."""
    env = os.environ.get("FLY_IN_PROJECT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def main(argv: list[str]) -> int:
    """Parse, plan and simulate the map given as the only argument."""
    if len(argv) != 2:
        print(f"usage: {argv[0]} MAP", file=sys.stderr)
        return 2
    root = project_root()
    if not (root / "src").is_dir():
        print(f"no project found at {root} (set FLY_IN_PROJECT)",
              file=sys.stderr)
        return 2
    sys.path.insert(0, str(root))
    os.chdir(root)
    from src.input_parsing import input_parsing
    from src.pathfinding_algorithm import CustomException
    from src.simulation_engine import build_scheduler

    config = input_parsing(argv[1])
    try:
        log = build_scheduler(config).run()
    except CustomException as error:
        print(error, file=sys.stderr)
        return 1
    print("\n".join(log))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
