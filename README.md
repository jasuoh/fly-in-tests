# fly-in-tests

A tester for the 42 **Fly-In** project. It runs your program on 125 maps and
checks whether what it prints (in the terminal, or in an output file) is a
**valid solution**. It also checks that broken maps are rejected cleanly.

It is a *black box* tester: it starts your program as a command, reads the
turn lines it prints, and replays them against the rules of the subject with
its own, independent checker. Nothing from your code is trusted.

Requirements: Python 3.10 or newer, no third-party packages.

## Quick start

```sh
git clone git@github.com:jasuoh/fly-in-tests.git
cd fly-in-tests

# any program that takes a map path and prints the turns:
python3 -m fly_in_tester run --cmd "python3 main.py {map}" --cwd ../my-project
```

`{map}` is replaced by the path of each map. Useful options:

| Option | Meaning |
| --- | --- |
| `--cwd DIR` | working directory of your program |
| `--timeout N` | seconds per map (default 60) |
| `--jobs N` | run N maps in parallel |
| `--group G` / `--filter TEXT` | only some maps (`provided`, `provided-invalid`, `edge-valid`, `edge-invalid`) |
| `--source file` or `{out}` in `--cmd` | read the solution from a file your program writes (see below) |
| `--strict-output` | fail if your program prints anything besides turn lines |
| `--strict-targets` | turns above the reference target become failures, not warnings |
| `--no-check-lines` | do not require the line number in error messages |
| `--shell` | run `--cmd` through the shell (pipes, `&&`, ...) |
| `-v`, `--json`, `--no-color` | output control |

The exit status is `1` if any map **fails**, `0` otherwise (warnings do not
change it).

### Makefile

`make` (or `make help`) lists the targets:

| Target | What it does |
| --- | --- |
| `make run` | run the tester on all maps; options `CMD`, `GROUP`, `FILTER`, `JOBS`, `TIMEOUT`, `ARGS` |
| `make run-strict` | like `run`, but turns above the targets are failures |
| `make list` | list the maps (`GROUP`, `FILTER`) |
| `make check MAP=<map> OUT=<file or ->` | check an existing output |
| `make test` | tests of the tester itself |
| `make whitebox` | unit tests of the project (`PROJECT=<path>`) |
| `make lint` | `flake8` and `mypy --strict` |
| `make all` | `lint` + `test` + `whitebox` |
| `make maps` | regenerate `maps/` and `manifest.json` |
| `make clean` | remove caches |

```sh
make run                                    # author's project through the adapter
make run GROUP=edge-invalid                 # only the invalid edge cases
make run CMD="python3 main.py {map}" ARGS="--cwd ../my-project"
```

### Terminal output or output file

- **Terminal (default):** every stdout line that looks like a turn
  (`D1-roof1 D2-corridorA`) is collected; banners and other text are ignored.
- **File:** put `{out}` in the command, e.g.
  `--cmd "python3 main.py {map} {out}"`. Your program must write the turns to
  that path; the terminal is then not used for the solution.

To check an output you already have:

```sh
python3 -m fly_in_tester check maps/provided/easy/01_linear_path.txt output.txt
python3 main.py maps/provided/easy/01_linear_path.txt | python3 -m fly_in_tester check maps/provided/easy/01_linear_path.txt -
```

### Programs with a GUI

A tester cannot click through a window. If your program opens one, give it a
way to print without it (for example a `--no-gui` flag) and use that in
`--cmd`, or use an adapter (see below). The tester already sets
`SDL_VIDEODRIVER=dummy`.

## Testing a project with a different structure

The tester does not care how a project is organised, only that it can be run
as a **command**. The contract:

1. the command takes the map (as an argument, on stdin, or via `{map}`);
2. for a solvable map it prints the turns, one line per turn
   (`D1-roof1 D2-corridorA`), to the terminal or to a file, and exits with
   status **0**;
3. for a broken or unsolvable map it prints a message (with the line number
   for parse errors) to stderr and exits with a status **other than 0**;
4. it never opens a window and never crashes with a traceback.

Then only the command changes. `{map}` is the map path, `{out}` a file the
program should write:

| Project | `--cmd` |
| --- | --- |
| script, map as argument | `python3 main.py {map}` |
| package | `python3 -m fly_in {map}` |
| program with an option | `python3 main.py --map {map} --no-gui` |
| compiled program | `./fly_in {map}` |
| map on stdin (needs `--shell`) | `./fly_in < {map}` |
| solution written to a file | `python3 main.py {map} {out}` |

```sh
make run PROJECT=../other-project CMD="python3 main.py {map}"
make run PROJECT=../other-project CMD="./fly_in < {map}" ARGS=--shell
```

`PROJECT` is the directory the command runs in (`--cwd`). Use `-v` to see the
details of a failure and `make run GROUP=edge-invalid` to focus on parser
errors.

If the project's entry point cannot be used (it opens a window, or asks
questions), write a small adapter. `adapters/template.py` is a fill-in
template for Python projects: it calls your parser and simulation and prints
the turns. `adapters/fly_in_project.py` is a finished example.

## How a map is judged

| Map kind | Expected behaviour | Result |
| --- | --- | --- |
| **valid** (must be solved) | exit status 0, no traceback, and a solution the checker accepts | `PASS`; `WARN` if it uses more turns than the reference target or ignores a priority zone; otherwise `FAIL` |
| **invalid** (must be rejected) | non-zero exit status, no traceback and no crash, a message on stderr that names the line of the mistake, and **no** solution printed | `PASS`, else `FAIL` |

Each map has a level. `required` maps must behave as described. `recommended`
maps are debatable readings of the subject (tabs between fields, comments
after a definition, a missing `]`, ...): a deviation is only a `WARN`.

## What the checker verifies

Every line is one turn; a token is `D<id>-<zone>` or, for a two-turn flight
into a restricted zone, `D<id>-<from>-<to>`. The checker fails a solution
when:

- a drone acts twice in a turn, or a token is malformed;
- ids are not `D0..D(n-1)` or `D1..Dn`;
- a move uses a missing connection, enters a **blocked** zone, or enters a
  **restricted** zone without the flight notation;
- a drone in flight does not land in the **next** turn;
- a zone holds more than `max_drones` drones at the end of a turn (start and
  end are unlimited; a drone leaving frees its place in the same turn);
- a connection carries more than `max_link_capacity` drones in a turn
  (departures in both directions; a drone landing from a flight frees the
  connection in the same turn);
- a delivered drone moves again, a turn line is empty, or not every drone
  ends in the end zone.

Zone capacity counts only drones that have landed; drones in flight are not
counted against the destination until they arrive.

## The maps

`maps/manifest.json` describes every map (expected behaviour, reference
target, acceptable error lines, level). 125 maps in four groups:

| Group | Maps | Content |
| --- | --- | --- |
| `provided` | 28 | the maps of the subject (easy, medium, hard, challenger, critical, extra) with the reference targets |
| `provided-invalid` | 10 | the deliberately broken maps that come with them |
| `edge-valid` | 29 | valid edge cases: comments, CRLF, negative coordinates, huge capacities, 100 and 10000 drones, restricted chains, blocked bypasses, grids, ... |
| `edge-invalid` | 58 | every parser rule of the subject broken one by one, plus maps without a solution (blocked start/end/only route, disconnected, no connections) |

Reference targets are the subject's "≤ N turns" values; the challenger map
uses 44 (beating the record of 45) and is optional.

`tools/build_maps.py` regenerates `maps/` and the manifest. Add your own case
in that file (or a map and a manifest entry) and run
`python3 tools/build_maps.py --project ../your-project`.

## Adapter for the author's project

`make run` uses this adapter by default, so the project itself needs no
changes:

```sh
python3 -m fly_in_tester run --cmd "python3 adapters/fly_in_project.py {map}"
```

`adapters/fly_in_project.py` runs parse, plan and simulate of a project that
provides `src.input_parsing.input_parsing` and
`src.simulation_engine.build_scheduler` and prints the turn log. The project is
taken from `$FLY_IN_PROJECT`, by default the folder that contains this
repository (`project/fly-in-tests`).

## White-box tests (unittest)

`whitebox/` holds unit tests that import the project's own modules: parser
edge cases (including exact error lines and causes), blocked zones, movement
rules, the Pygame view (with a dummy video driver) and the retry button.

```sh
python3 -m unittest discover -s whitebox -t . -v            # FLY_IN_PROJECT optional
```

## Tests of the tester

The checker, the reader, the manifest and the runner have their own tests, so
the verdicts can be trusted:

```sh
python3 -m unittest discover -s tests -t . -v
python3 -m flake8 . && python3 -m mypy .
```

## Layout

```
fly_in_tester/   mapfile.py  (independent map reader)
                 checker.py  (solution checker)
                 runner.py   (runs the program, judges the result)
                 __main__.py (command line: run, check, list)
Makefile         shortcuts (make help)
maps/            provided/, edge/, manifest.json
adapters/        fly_in_project.py (finished example), template.py (fill-in)
tools/           build_maps.py
tests/           tests of the tester
whitebox/        unit tests for the project under test
```
