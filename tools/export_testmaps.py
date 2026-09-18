"""Export a simple, shareable folder of commented test maps.

Usage: python tools/export_testmaps.py --out DIR [--project PROJECT]

Every map gets a comment header that says what is expected and what to watch
for. The header adds lines at the top, so the expected error lines of the
invalid maps are shifted accordingly (the header states the right line).
"""

import argparse
import importlib
import json
import shutil
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "maps"

EASY = [
    "provided/easy/01_linear_path", "provided/easy/02_simple_fork",
    "provided/easy/03_basic_capacity", "edge/valid/single_drone_linear",
    "edge/valid/link_capacity_two", "edge/valid/priority_preferred",
    "edge/valid/blocked_bypass", "edge/valid/blocked_isolated",
    "edge/valid/metadata_any_order", "edge/valid/negative_coordinates",
    "edge/valid/comments_and_blank_lines", "edge/valid/crlf_line_endings",
    "edge/valid/no_trailing_newline", "edge/valid/no_space_after_colon",
    "edge/valid/unicode_zone_name", "edge/valid/start_capacity_equals_drones",
    "edge/valid/unknown_color_name",
]
MEDIUM = [
    "provided/medium/01_dead_end_trap", "provided/medium/02_circular_loop",
    "provided/medium/03_priority_puzzle",
    "provided/critical/01_restricted_gate_contention",
    "provided/critical/02_conveyor_chain",
    "provided/critical/03_link_vs_zone_capacity",
    "provided/critical/04_symmetric_deadlock_risk",
    "edge/valid/restricted_chain", "edge/valid/restricted_beats_long_detour",
    "edge/valid/fork_merge_bottleneck", "edge/valid/parallel_paths_three",
    "edge/valid/long_chain_20", "edge/valid/huge_capacities",
    "provided/extra/04_simple_fork_two_paths",
    "provided/extra/05_single_capacity_choke",
    "provided/extra/06_oscillation_trap",
    "provided/extra/07_priority_tiebreak",
    "provided/extra/08_restricted_capacity_relay",
    "provided/extra/12_dead_end_decoy", "provided/extra/13_equal_cost_paths",
    "provided/extra/14_shorter_path_preference",
]
HARD = [
    "provided/hard/01_maze_nightmare", "provided/hard/02_capacity_hell",
    "provided/hard/03_ultimate_challenge",
    "provided/challenger/01_the_impossible_dream",
    "provided/extra/01_complex_maze", "provided/extra/03_challenge_x3",
    "edge/valid/grid_4x4_10_drones", "edge/valid/many_drones_100",
    "edge/valid/many_drones_10000",
]
TRICKY = [
    "edge/valid/indented_comment", "edge/valid/whitespace_only_line",
    "edge/valid/inline_comment", "edge/valid/tab_separated_fields",
    "edge/valid/double_space_fields", "edge/valid/utf8_bom",
    "edge/invalid/unclosed_bracket", "edge/invalid/metadata_without_brackets",
    "edge/invalid/two_metadata_blocks", "edge/invalid/duplicate_metadata_key",
    "edge/invalid/spaces_around_equals", "edge/invalid/zone_type_wrong_case",
    "edge/invalid/start_capacity_below_drones",
]

# What matters for a map, in one or two sentences.
NOTES = {
    "easy/01_linear_path": "A straight line. Checks the output format "
    "D<ID>-<zone> and that drones queue behind each other (capacity 1).",
    "easy/02_simple_fork": "Two paths from a junction (capacity 2). Drones "
    "must spread out; path_c is a dead end nobody should use.",
    "easy/03_basic_capacity": "First zones with a capacity limit. A drone "
    "that cannot move is simply left out of the turn line.",
    "medium/01_dead_end_trap": "Dead ends. Do not send drones into them; "
    "they would block a capacity-1 zone forever.",
    "medium/02_circular_loop": "Restricted zones take 2 turns: the drone "
    "shows up as D<ID>-<from>-<to> first and lands one turn later. The "
    "loop is a trap: going around is slower than the direct way.",
    "medium/03_priority_puzzle": "Priority zones cost the same 1 turn but "
    "should be preferred when the length is equal.",
    "critical/01_restricted_gate_contention": "Two staging zones feed one "
    "restricted zone: capacity must be reserved for drones in flight.",
    "critical/02_conveyor_chain": "A capacity-1 tunnel. A drone may enter a "
    "zone in the same turn the drone in it leaves.",
    "critical/03_link_vs_zone_capacity": "The connection capacity is the "
    "real bottleneck here, not the zones.",
    "critical/04_symmetric_deadlock_risk": "Two symmetric arms compete for "
    "one restricted zone. Naive schedulers deadlock.",
    "hard/01_maze_nightmare": "Many traps and loops. Needs real "
    "path-finding, no greedy walking.",
    "hard/02_capacity_hell": "12 drones and tight capacities everywhere. "
    "Timing matters more than the route.",
    "hard/03_ultimate_challenge": "All mechanics together.",
    "challenger/01_the_impossible_dream": "OPTIONAL. 25 drones, extreme "
    "bottlenecks. The reference record is 45 turns; beating it is a bonus.",
}
DESC = {
    "single_drone_linear": "One drone, straight line: 2 turns.",
    "link_capacity_two": "Zone and connection capacity 2: both drones "
    "must move together, not one after the other.",
    "priority_preferred": "Two equal routes; the one through the priority "
    "zone p should be taken.",
    "blocked_bypass": "A blocked zone has connections. It is valid input; "
    "the drones must simply go around it.",
    "blocked_isolated": "A blocked zone nobody connects to. Must not "
    "cause an error.",
    "metadata_any_order": "Metadata keys in any order "
    "([max_drones=2 color=blue zone=priority]).",
    "negative_coordinates": "Coordinates may be negative.",
    "comments_and_blank_lines": "Comments and empty lines everywhere.",
    "crlf_line_endings": "Windows line endings (CRLF).",
    "no_trailing_newline": "The last line has no newline.",
    "no_space_after_colon": "'hub:a 1 0' without a space after the colon.",
    "unicode_zone_name": "A zone name with a non-ASCII character.",
    "start_capacity_equals_drones": "start_hub has max_drones equal to "
    "nb_drones: allowed.",
    "unknown_color_name": "color=rainbow is not a real color. Colors are "
    "free text: it must not crash the program or the window.",
    "restricted_chain": "Three restricted zones in a row: each hop takes "
    "2 turns and a drone must land the turn after it starts.",
    "restricted_beats_long_detour": "A restricted shortcut (2 turns) still "
    "beats a long normal detour.",
    "fork_merge_bottleneck": "Two paths that merge into one capacity-1 "
    "zone.",
    "parallel_paths_three": "Three parallel paths; use all of them.",
    "long_chain_20": "A chain of 20 zones with 3 drones: they must follow "
    "each other without gaps.",
    "huge_capacities": "max_drones and max_link_capacity of 1000000000 "
    "must not cause problems.",
    "grid_4x4_10_drones": "A 4x4 grid, 10 drones, capacity 2.",
    "many_drones_100": "100 drones through a chain: 101 turns is optimal.",
    "many_drones_10000": "SLOW. 10000 drones: there is no upper limit on "
    "the number of drones.",
    "indented_comment": "A comment line that starts with spaces.",
    "whitespace_only_line": "A line that contains only spaces.",
    "inline_comment": "A comment after a zone definition.",
    "tab_separated_fields": "Tabs instead of spaces between the fields.",
    "double_space_fields": "Two spaces between the fields.",
    "utf8_bom": "The file starts with a UTF-8 byte order mark.",
    "unclosed_bracket": "The metadata block is missing its ].",
    "metadata_without_brackets": "key=value without [ ].",
    "two_metadata_blocks": "Two [ ] blocks on one line.",
    "duplicate_metadata_key": "The same key twice in one block.",
    "spaces_around_equals": "'zone = normal' with spaces around =.",
    "zone_type_wrong_case": "zone=Normal (upper case) is not a valid type.",
    "start_capacity_below_drones": "start_hub cannot hold all the drones.",
}
UNSOLVABLE_WHY = "The map is well-formed but has NO solution. The program " \
    "must print an error (for example 'no path') and exit with a status " \
    "other than 0, and it must not print any turns."


def wrap(text: str, first: str, rest: str = "") -> list[str]:
    """Wrap ``text`` for a comment line."""
    return textwrap.wrap(text, width=74, initial_indent=first,
                         subsequent_indent=rest or " " * len(first))


def build_header(lines: list[str], newline: str) -> str:
    """Turn header lines into comment lines."""
    rule = "# " + "=" * 68
    body = [rule] + [("# " + line).rstrip() for line in lines] + [rule]
    return newline.join(body) + newline


def read_entries() -> dict[str, dict[str, Any]]:
    """Return the manifest entries keyed by path without the suffix."""
    data = json.loads((MAPS / "manifest.json").read_text("utf-8"))["maps"]
    return {e["path"][:-4]: e for e in data}


def reference_turns(project: Path | None, path: Path) -> int | None:
    """Return the number of turns of a solution the project finds."""
    if project is None:
        return None
    sys.path.insert(0, str(project))
    parsing = importlib.import_module("src.input_parsing")
    engine = importlib.import_module("src.simulation_engine")
    try:
        config = parsing.input_parsing(str(path))
        return len(engine.build_scheduler(config).run())
    except SystemExit:
        return None


def make_map(
    key: str, entry: dict[str, Any], tricky: bool, project: Path | None
) -> str | bytes:
    """Return the new content of a map: comment header plus the map."""
    raw = (MAPS / (key + ".txt")).read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    if not text.strip():
        return raw
    name = key.split("/")[-1]
    short = key.split("/", 1)[1] if key.startswith("provided/") else name
    newline = "\r\n" if "\r\n" in text else "\n"
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    text = text.lstrip("\ufeff")
    lines = [f"TEST MAP: {short}"]
    line_numbers: list[int] = []
    if entry["expect"] == "solve":
        if tricky:
            lines += wrap("EXPECTED: arguable. A valid map that stricter "
                          "parsers may reject. It is not a failure to "
                          "reject it, but be ready to explain why.", "")
        else:
            lines += wrap("EXPECTED: must be SOLVED. No error, every drone "
                          "reaches the end zone.", "")
        if entry.get("target") is not None:
            lines += wrap(f"TURNS: reference target <= {entry['target']}.",
                          "")
        turns = reference_turns(project, MAPS / (key + ".txt"))
        if turns is not None:
            lines += wrap(f"A valid solution with {turns} turns exists.", "")
        why = NOTES.get(short) or DESC.get(name) or entry.get("note", "")
        if why:
            lines += wrap("NOTE: " + why, "")
        lines += wrap("WATCH: every turn is one line; only drones that move "
                      "are listed; the capacity and connection limits hold "
                      "in every single turn.", "")
    else:
        if entry.get("reason") == "unsolvable":
            lines += wrap("EXPECTED: " + UNSOLVABLE_WHY, "")
        else:
            lines += wrap("EXPECTED: must be REJECTED. Exit status other "
                          "than 0, a clear message with the line number and "
                          "the cause, no traceback, no turns printed.", "")
        why = DESC.get(name) or entry.get("note") or name.replace("_", " ")
        lines += wrap("WHY: " + why[0].upper() + why[1:], "")
        if tricky:
            lines += wrap("Arguable: the subject asks for syntactically "
                          "valid metadata, so rejecting this is the "
                          "recommended behaviour.", "")
        wanted = entry.get("line")
        if entry.get("reason") != "unsolvable" and wanted:
            line_numbers = wanted if isinstance(wanted, list) else [wanted]
    shift = 0
    for _ in range(5):
        current = list(lines)
        if line_numbers:
            shown = " or ".join(str(n + shift) for n in line_numbers)
            current += wrap(f"LINE: the mistake is on line {shown} of this "
                            "file (the comment header is counted).", "")
        header = build_header(current, newline)
        if header.count(newline) == shift:
            break
        shift = header.count(newline)
    return bom + header + text


README = (Path(__file__).parent / "testmaps_README.md").read_text(
    encoding="utf-8")


def export(out: Path, project: Path | None) -> None:
    """Write the folder of commented maps and its README."""
    if out.exists():
        shutil.rmtree(out)
    entries = read_entries()
    folders: dict[str, list[str]] = {
        "easy": EASY, "medium": MEDIUM, "hard": HARD, "tricky": TRICKY}
    parser_maps, nosol_maps = [], []
    for key, entry in entries.items():
        if entry["expect"] != "error" or key in TRICKY:
            continue
        if entry.get("reason") == "unsolvable":
            nosol_maps.append(key)
        else:
            parser_maps.append(key)

    def order(key: str) -> tuple[bool, str]:
        return (not key.startswith("provided"), key)

    folders["invalid/parser"] = sorted(parser_maps, key=order)
    folders["invalid/no_solution"] = sorted(nosol_maps, key=order)
    counts: dict[str, int] = {}
    for folder, keys in folders.items():
        for number, key in enumerate(keys, 1):
            content = make_map(key, entries[key], folder == "tricky", project)
            name = key.split("/")[-1]
            if name[:2].isdigit():
                name = name.split("_", 1)[1]
            target = out / folder / f"{number:02d}_{name}.txt"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(
                content if isinstance(content, bytes)
                else content.encode("utf-8"))
        counts[folder] = len(keys)
    (out / "README.md").write_text(README.format(
        total=sum(counts.values()), easy=counts["easy"],
        medium=counts["medium"], hard=counts["hard"],
        parser=counts["invalid/parser"], nosol=counts["invalid/no_solution"],
        tricky=counts["tricky"]), encoding="utf-8")
    print(f"wrote {sum(counts.values())} maps to {out}: {counts}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--project", type=Path, default=ROOT.parent)
    args = parser.parse_args()
    project = args.project if (args.project / "src").is_dir() else None
    export(args.out, project)
