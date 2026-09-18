"""Generate maps/ (edge cases, provided maps) and maps/manifest.json.

Usage: python tools/build_maps.py [--project PATH_TO_PROJECT_WITH_maps/]
"""

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
MAPS = ROOT / "maps"

BASE = (
    "nb_drones: 2\n"
    "start_hub: s 0 0 [color=green]\n"
    "hub: a 1 0\n"
    "end_hub: g 2 0 [color=red]\n"
    "connection: s-a\n"
    "connection: a-g\n"
)

# Reference targets from the subject (turns), by path below maps/provided/.
TARGETS = {
    "easy/01_linear_path": 6, "easy/02_simple_fork": 6,
    "easy/03_basic_capacity": 8, "medium/01_dead_end_trap": 15,
    "medium/02_circular_loop": 20, "medium/03_priority_puzzle": 12,
    "hard/01_maze_nightmare": 45, "hard/02_capacity_hell": 60,
    "hard/03_ultimate_challenge": 35,
}
# "Beat the record of 45" means at most 44 turns; purely optional.
CHALLENGER = "challenger/01_the_impossible_dream"

# Invalid maps that are well-formed but have no solution.
UNSOLVABLE = {
    "05_unreachable_goal", "disconnected_goal", "no_connections",
    "only_path_is_blocked", "start_is_blocked", "end_is_blocked",
    "blocked_wall",
}

PROVIDED_INVALID: dict[str, dict[str, Any]] = {
    "01_missing_nb_drones": {"note": "nb_drones line is missing"},
    "02_undefined_zone_reference": {"line": 7, "note": "unknown zone"},
    "03_duplicate_zone_name": {"line": 6, "note": "zone defined twice"},
    "04_invalid_zone_type": {"line": 5, "note": "unknown zone type"},
    "05_unreachable_goal": {"note": "no route to the goal"},
    "06_zero_capacity_zone": {"line": 6, "note": "max_drones=0"},
    "07_zero_drones": {"line": 2, "note": "nb_drones is 0"},
    "08_malformed_line": {"line": 5, "note": "line without ':'"},
    "09_duplicate_connection": {"line": 11, "note": "a-b then b-a"},
    "10_dash_in_zone_name": {"line": [6, 9, 10], "note": "dash in a name"},
}


def sub(old: str, new: str, base: str = BASE) -> str:
    """Return ``base`` with ``old`` replaced by ``new``."""
    assert old in base, old
    return base.replace(old, new)


def chain(hubs: int, drones: int, kind: str = "") -> str:
    """Return a straight chain start - h1 ... hN - end."""
    lines = [f"nb_drones: {drones}", "start_hub: s 0 0"]
    names = [f"h{i}" for i in range(1, hubs + 1)]
    lines += [f"hub: {n} {i} 0{kind}" for i, n in enumerate(names, 1)]
    lines.append(f"end_hub: g {hubs + 1} 0")
    path = ["s", *names, "g"]
    lines += [f"connection: {a}-{b}" for a, b in zip(path, path[1:])]
    return "\n".join(lines) + "\n"


def grid(size: int, drones: int, cap: int) -> str:
    """Return a size x size grid, start top-left, end bottom-right."""
    name = {(x, y): f"n{x}_{y}" for x in range(size) for y in range(size)}
    last = (size - 1, size - 1)
    lines = [f"nb_drones: {drones}", f"start_hub: {name[(0, 0)]} 0 0"]
    for (x, y), n in name.items():
        if (x, y) not in ((0, 0), last):
            lines.append(f"hub: {n} {x} {y} [max_drones={cap}]")
    lines.append(f"end_hub: {name[last]} {last[0]} {last[1]}")
    for (x, y), n in name.items():
        for dx, dy in ((1, 0), (0, 1)):
            other = name.get((x + dx, y + dy))
            if other:
                lines.append(f"connection: {n}-{other}")
    return "\n".join(lines) + "\n"


VALID: dict[str, dict[str, Any]] = {
    "single_drone_linear": {
        "text": sub("nb_drones: 2", "nb_drones: 1"), "target": 2},
    "comments_and_blank_lines": {"text": (
        "# header\n\n" + sub("hub: a", "# a comment\n\nhub: a") + "# end\n")},
    "crlf_line_endings": {"text": BASE.replace("\n", "\r\n")},
    "no_trailing_newline": {"text": BASE.rstrip("\n")},
    "no_space_after_colon": {"text": BASE.replace(": ", ":")},
    "metadata_any_order": {"text": sub(
        "hub: a 1 0", "hub: a 1 0 [max_drones=2 color=blue zone=priority]")},
    "negative_coordinates": {"text": sub("hub: a 1 0", "hub: a -4 -7")},
    "huge_capacities": {"text": sub(
        "nb_drones: 2", "nb_drones: 30").replace(
        "hub: a 1 0", "hub: a 1 0 [max_drones=1000000000]").replace(
        "connection: s-a", "connection: s-a [max_link_capacity=1000000000]"
    ).replace("connection: a-g",
              "connection: a-g [max_link_capacity=1000000000]"),
        "target": 2},
    "many_drones_100": {"text": sub("nb_drones: 2", "nb_drones: 100"),
                        "target": 101},
    "unicode_zone_name": {"text": BASE.replace("hub: a", "hub: zone_ä")
                          .replace("s-a", "s-zone_ä")
                          .replace("a-g", "zone_ä-g")},
    "link_capacity_two": {"text": (
        "nb_drones: 2\nstart_hub: s 0 0\nhub: a 1 0 [max_drones=2]\n"
        "end_hub: g 2 0\nconnection: s-a [max_link_capacity=2]\n"
        "connection: a-g [max_link_capacity=2]\n"), "target": 2},
    "start_capacity_equals_drones": {"text": sub(
        "start_hub: s 0 0 [color=green]", "start_hub: s 0 0 [max_drones=2]")},
    "restricted_chain": {"text": chain(3, 3, " [zone=restricted]")},
    "restricted_beats_long_detour": {"text": (
        "nb_drones: 1\nstart_hub: s 0 0\nhub: r 1 0 [zone=restricted]\n"
        "hub: n1 1 1\nhub: n2 2 1\nhub: n3 3 1\nend_hub: g 4 0\n"
        "connection: s-r\nconnection: r-g\nconnection: s-n1\n"
        "connection: n1-n2\nconnection: n2-n3\nconnection: n3-g\n"),
        "target": 3},
    "priority_preferred": {"text": (
        "nb_drones: 1\nstart_hub: s 0 0\nhub: n 1 0\n"
        "hub: p 1 1 [zone=priority]\nend_hub: g 2 0\n"
        "connection: s-n\nconnection: n-g\nconnection: s-p\n"
        "connection: p-g\n"), "target": 2, "prefer_visit": ["p"]},
    "blocked_bypass": {"text": (
        "nb_drones: 3\nstart_hub: s 0 0\nhub: x 1 0 [zone=blocked]\n"
        "hub: w 2 0\nend_hub: g 3 0\nconnection: s-x\nconnection: x-g\n"
        "connection: s-w\nconnection: w-g\n"), "target": 4},
    "blocked_isolated": {"text": sub(
        "hub: a 1 0", "hub: a 1 0\nhub: x 9 9 [zone=blocked]")},
    "long_chain_20": {"text": chain(19, 3), "target": 22},
    "fork_merge_bottleneck": {"text": (
        "nb_drones: 4\nstart_hub: s 0 0 [max_drones=4]\nhub: l 1 1\n"
        "hub: r 1 -1\nhub: m 2 0\nend_hub: g 3 0 [max_drones=4]\n"
        "connection: s-l\nconnection: s-r\nconnection: l-m\n"
        "connection: r-m\nconnection: m-g\n")},
    "grid_4x4_10_drones": {"text": grid(4, 10, 2)},
    "parallel_paths_three": {"text": (
        "nb_drones: 6\nstart_hub: s 0 0 [max_drones=6]\nhub: a 1 1\n"
        "hub: b 1 0\nhub: c 1 -1\nend_hub: g 2 0 [max_drones=6]\n"
        "connection: s-a\nconnection: s-b\nconnection: s-c\n"
        "connection: a-g\nconnection: b-g\nconnection: c-g\n"),
        "target": 4},
}

# Valid maps whose exact syntax is debatable: a failure is only a warning.
RECOMMENDED_VALID: dict[str, dict[str, Any]] = {
    "indented_comment": {"text": "  # indented comment\n" + BASE,
                         "note": "comment line with leading spaces"},
    "whitespace_only_line": {"text": sub("hub: a", "   \nhub: a"),
                             "note": "a line that only has spaces"},
    "inline_comment": {"text": sub("hub: a 1 0", "hub: a 1 0 # note"),
                       "note": "comment after a definition"},
    "tab_separated_fields": {"text": sub("hub: a 1 0", "hub: a\t1\t0"),
                             "note": "tabs between the fields"},
    "double_space_fields": {"text": sub("hub: a 1 0", "hub: a  1 0"),
                            "note": "two spaces between the fields"},
    "utf8_bom": {"text": "\ufeff" + BASE,
                 "note": "file starts with a BOM"},
    "many_drones_10000": {
        "text": sub("nb_drones: 2", "nb_drones: 10000"),
        "target": 10001,
        "note": "there is no upper limit on drones (slow)"},
    "unknown_color_name": {
        "text": sub("hub: a 1 0", "hub: a 1 0 [color=rainbow]"),
        "note": "color values are free-form"},
}


def bad(text: str | bytes, line: Any = None, note: str = "",
        level: str = "required") -> dict[str, Any]:
    """Describe an invalid map."""
    return {"text": text, "line": line, "note": note, "level": level}


NO_NB = BASE.replace("nb_drones: 2\n", "")
INVALID: dict[str, dict[str, Any]] = {
    "empty_file": bad("", note="empty file"),
    "only_comments": bad("# a\n# b\n", note="no content"),
    "missing_nb_drones": bad(NO_NB, note="nb_drones missing"),
    "nb_drones_not_first_line": bad(NO_NB + "nb_drones: 2\n", [1, 6],
                                    "nb_drones must be the first line"),
    "nb_drones_zero": bad(sub("nb_drones: 2", "nb_drones: 0"), 1, "0 drones"),
    "nb_drones_negative": bad(sub("nb_drones: 2", "nb_drones: -3"), 1),
    "nb_drones_text": bad(sub("nb_drones: 2", "nb_drones: many"), 1),
    "nb_drones_float": bad(sub("nb_drones: 2", "nb_drones: 1.5"), 1),
    "nb_drones_empty_value": bad(sub("nb_drones: 2", "nb_drones:"), 1),
    "nb_drones_twice": bad(BASE + "nb_drones: 3\n", [1, 7],
                           "nb_drones defined twice"),
    "missing_start_hub": bad(sub("start_hub: s 0 0 [color=green]",
                                 "hub: s 0 0"), note="no start_hub"),
    "missing_end_hub": bad(sub("end_hub: g 2 0 [color=red]", "hub: g 2 0"),
                           note="no end_hub"),
    "two_start_hubs": bad(BASE + "start_hub: x 5 5\n", [2, 7]),
    "two_end_hubs": bad(BASE + "end_hub: x 5 5\n", [4, 7]),
    "invalid_zone_type": bad(sub("hub: a 1 0", "hub: a 1 0 [zone=lava]"), 3),
    "empty_zone_type": bad(sub("hub: a 1 0", "hub: a 1 0 [zone=]"), 3),
    "max_drones_zero": bad(sub("hub: a 1 0", "hub: a 1 0 [max_drones=0]"), 3),
    "max_drones_negative": bad(
        sub("hub: a 1 0", "hub: a 1 0 [max_drones=-2]"), 3),
    "max_drones_text": bad(sub("hub: a 1 0", "hub: a 1 0 [max_drones=x]"), 3),
    "max_drones_float": bad(
        sub("hub: a 1 0", "hub: a 1 0 [max_drones=1.5]"), 3),
    "link_capacity_zero": bad(sub(
        "connection: s-a", "connection: s-a [max_link_capacity=0]"), 5),
    "link_capacity_negative": bad(sub(
        "connection: s-a", "connection: s-a [max_link_capacity=-1]"), 5),
    "link_capacity_text": bad(sub(
        "connection: s-a", "connection: s-a [max_link_capacity=x]"), 5),
    "duplicate_zone_name": bad(sub("hub: a 1 0", "hub: a 1 0\nhub: a 5 5"),
                               4, "second definition of a"),
    "duplicate_of_start_name": bad(sub("hub: a 1 0", "hub: s 1 0"), [2, 3]),
    "duplicate_connection": bad(BASE + "connection: s-a\n", 7),
    "duplicate_connection_reversed": bad(BASE + "connection: a-s\n", 7,
                                         "a-b and b-a are duplicates"),
    "dash_in_zone_name": bad(sub("hub: a 1 0", "hub: a-b 1 0"), [3, 5, 6],
                             "names must not contain dashes"),
    "coordinates_float": bad(sub("hub: a 1 0", "hub: a 1.5 0"), 3),
    "coordinates_text": bad(sub("hub: a 1 0", "hub: a x y"), 3),
    "coordinates_missing_y": bad(sub("hub: a 1 0", "hub: a 1"), 3),
    "coordinates_missing_both": bad(sub("hub: a 1 0", "hub: a"), 3),
    "self_connection": bad(BASE + "connection: a-a\n", 7),
    "connection_unknown_zone": bad(BASE + "connection: a-zzz\n", 7),
    "connection_before_zone_definition": bad(
        "nb_drones: 2\nstart_hub: s 0 0\nconnection: s-a\nhub: a 1 0\n"
        "end_hub: g 2 0\nconnection: a-g\n", 3,
        "connections may only use previously defined zones"),
    "connection_without_dash": bad(BASE + "connection: sa\n", 7),
    "connection_three_parts": bad(BASE + "connection: s-a-g\n", 7),
    "connection_empty": bad(BASE + "connection:\n", 7),
    "connection_trailing_dash": bad(BASE + "connection: s-\n", 7),
    "unknown_key": bad(BASE + "foo: bar\n", 7),
    "line_without_colon": bad(BASE + "this is not a line\n", 7),
    "unknown_zone_metadata": bad(
        sub("hub: a 1 0", "hub: a 1 0 [speed=3]"), 3),
    "metadata_without_equals": bad(sub("hub: a 1 0", "hub: a 1 0 [zone]"), 3),
    "unknown_connection_metadata": bad(
        sub("connection: s-a", "connection: s-a [foo=1]"), 5),
    "binary_garbage": bad(bytes(range(256)), note="not text at all"),
    "disconnected_goal": bad(sub("connection: a-g\n", ""),
                             note="goal cannot be reached"),
    "no_connections": bad(
        sub("connection: s-a\n", "").replace("connection: a-g\n", ""),
        note="no connection at all"),
    "only_path_is_blocked": bad(
        sub("hub: a 1 0", "hub: a 1 0 [zone=blocked]"),
        note="the only route is blocked"),
    "start_is_blocked": bad(sub(
        "start_hub: s 0 0 [color=green]", "start_hub: s 0 0 [zone=blocked]"),
        note="start hub is blocked"),
    "end_is_blocked": bad(sub(
        "end_hub: g 2 0 [color=red]", "end_hub: g 2 0 [zone=blocked]"),
        note="end hub is blocked"),
    "blocked_wall": bad(
        "nb_drones: 1\nstart_hub: s 0 0\nhub: x 1 0 [zone=blocked]\n"
        "hub: y 1 1 [zone=blocked]\nend_hub: g 2 0\nconnection: s-x\n"
        "connection: s-y\nconnection: x-g\nconnection: y-g\n",
        note="every route crosses a blocked zone"),
    # Debatable: the subject asks for syntactically valid metadata blocks.
    "unclosed_bracket": bad(sub("hub: a 1 0", "hub: a 1 0 [zone=normal"), 3,
                            "missing ]", "recommended"),
    "metadata_without_brackets": bad(
        sub("hub: a 1 0", "hub: a 1 0 zone=normal"), 3,
        "metadata must be in [...]", "recommended"),
    "two_metadata_blocks": bad(
        sub("hub: a 1 0", "hub: a 1 0 [zone=normal] [color=red]"), 3,
        "only one block", "recommended"),
    "duplicate_metadata_key": bad(
        sub("hub: a 1 0", "hub: a 1 0 [zone=normal zone=blocked]"), 3,
        "key given twice", "recommended"),
    "spaces_around_equals": bad(
        sub("hub: a 1 0", "hub: a 1 0 [zone = normal]"), 3,
        "key = value", "recommended"),
    "zone_type_wrong_case": bad(
        sub("hub: a 1 0", "hub: a 1 0 [zone=Normal]"), 3,
        "types are lower case", "recommended"),
    "start_capacity_below_drones": bad(sub(
        "start_hub: s 0 0 [color=green]", "start_hub: s 0 0 [max_drones=1]"),
        2, "start cannot hold all drones", "recommended"),
}


def write(path: Path, text: str | bytes) -> None:
    """Write text (exactly, keeping line endings) or bytes to ``path``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_bytes(text.encode("utf-8"))


def build(project: Path | None) -> None:
    """Rebuild maps/ and the manifest."""
    if MAPS.exists():
        for child in MAPS.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    manifest: list[dict[str, Any]] = []

    if project is not None:
        for source in sorted((project / "maps").rglob("*.txt")):
            relative = source.relative_to(project / "maps").with_suffix("")
            key = relative.as_posix()
            target = MAPS / "provided" / source.relative_to(project / "maps")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if relative.parent.name == "invalid":
                info = PROVIDED_INVALID[relative.name]
                manifest.append({
                    "path": f"provided/{key}.txt", "group": "provided-invalid",
                    "expect": "error",
                    "reason": ("unsolvable" if relative.name in UNSOLVABLE
                               else "syntax"), **info})
                continue
            entry: dict[str, Any] = {
                "path": f"provided/{key}.txt", "group": "provided",
                "expect": "solve"}
            if key in TARGETS:
                entry["target"] = TARGETS[key]
            if key == CHALLENGER:
                entry.update(target=44, optional_target=True,
                             note="optional: beat the record of 45 turns")
            manifest.append(entry)

    for name, spec in {**VALID, **RECOMMENDED_VALID}.items():
        recommended = name in RECOMMENDED_VALID
        path = MAPS / "edge" / "valid" / f"{name}.txt"
        write(path, spec["text"])
        entry = {"path": f"edge/valid/{name}.txt", "group": "edge-valid",
                 "expect": "solve"}
        for key in ("target", "prefer_visit", "note"):
            if key in spec:
                entry[key] = spec[key]
        if recommended:
            entry["level"] = "recommended"
        manifest.append(entry)

    for name, spec in INVALID.items():
        write(MAPS / "edge" / "invalid" / f"{name}.txt", spec["text"])
        entry = {"path": f"edge/invalid/{name}.txt", "group": "edge-invalid",
                 "expect": "error", "level": spec["level"],
                 "reason": "unsolvable" if name in UNSOLVABLE else "syntax"}
        if spec["line"] is not None:
            entry["line"] = spec["line"]
        if spec["note"]:
            entry["note"] = spec["note"]
        manifest.append(entry)

    (MAPS / "manifest.json").write_text(
        json.dumps({"version": 1, "maps": manifest}, indent=2) + "\n")
    print(f"wrote {len(manifest)} maps")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=ROOT.parent)
    args = parser.parse_args()
    build(args.project if (args.project / "maps").is_dir() else None)
