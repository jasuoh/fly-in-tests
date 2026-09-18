# Fly-In test maps

{total} maps to test a Fly-In implementation, sorted by difficulty. Every map
starts with a comment header (`# ...`) that says what is expected and what
to watch for. Comments are part of the format, so the files are valid input.

| Folder | Maps | What to expect |
| --- | --- | --- |
| `easy/` | {easy} | must be solved; basic rules and input syntax |
| `medium/` | {medium} | must be solved; restricted and priority zones, bottlenecks, traps |
| `hard/` | {hard} | must be solved; complex maps and many drones (`challenger` is optional) |
| `invalid/parser/` | {parser} | must be rejected: broken syntax or rules |
| `invalid/no_solution/` | {nosol} | well-formed, but there is no solution: must be reported |
| `tricky/` | {tricky} | arguable cases: not a failure either way, but be ready to explain |

Files are numbered inside each folder; the name after the number tells what
it is about.

## How to test

Run your program on a map and look at the terminal output:

    python3 main.py easy/01_linear_path.txt

**Valid maps** (`easy`, `medium`, `hard`):
- the program exits with status 0 and prints one line per turn;
- a token is `D<ID>-<zone>`, or `D<ID>-<from>-<to>` for a drone that is on
  its way to a restricted zone (it lands in the next turn);
- drones that do not move in a turn are not listed;
- no zone holds more than `max_drones` drones at the end of a turn (default
  1, start and end are unlimited) and no connection carries more than
  `max_link_capacity` drones in a turn (default 1);
- a restricted zone costs 2 turns, priority and normal cost 1, blocked zones
  are never entered;
- after the last drone arrived the output stops;
- fewer turns is better. Reference targets and turn counts of known
  solutions are in each header.

**Invalid maps** (`invalid/`):
- the program exits with a status other than 0;
- it prints a clear message with the **line number** and the cause;
- it never crashes with a traceback and never prints turns.

## Things to keep in mind

- The comment header shifts the line numbers. The header of each invalid
  map states the right line number *of that file*.
- Two files have no header because a header would change what they test:
  `invalid/parser/*_empty_file.txt` (an empty file) and
  `invalid/parser/*_binary_garbage.txt` (not text).
- The subject says `nb_drones` is the first line. Comment lines before it
  are fine (the provided maps start with one).
- Colors are free text. An unknown color must not crash the program.
- Zone names cannot contain dashes or spaces. A dash would break the
  `zone1-zone2` connection syntax.
- Drone ids may start at 0 or at 1; be consistent.
- Some maps are slow on purpose (`hard/*many_drones_10000`): there is no
  upper limit on the number of drones.
- A blocked zone is valid input, even with connections. It is only
  forbidden to enter it.
