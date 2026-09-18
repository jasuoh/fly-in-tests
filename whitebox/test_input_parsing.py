"""White-box unit tests for the project's map parser (input edge cases)."""

import contextlib
import glob
import io
import os
import tempfile
import unittest

from . import _project
from src.input_parsing import Config_Map, input_parsing, zone_types

BASE = (
    "nb_drones: 2\n"
    "start_hub: s 0 0 [color=green]\n"
    "hub: a 1 0\n"
    "end_hub: g 2 0 [color=red]\n"
    "connection: s-a\n"
    "connection: a-g\n"
)
# Line numbers in BASE: nb_drones=1, start=2, hub a=3, end=4, s-a=5, a-g=6


def edit(old: str, new: str) -> str:
    """Return BASE with ``old`` replaced by ``new``."""
    assert old in BASE, old
    return BASE.replace(old, new)


class ParserTestCase(unittest.TestCase):
    """Helpers shared by all parser tests."""

    def setUp(self) -> None:
        """Create a temporary directory for the map files."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def write(self, content: str | bytes) -> str:
        """Write ``content`` to a map file and return its path."""
        path = os.path.join(self._tmp.name, 'map.txt')
        if isinstance(content, bytes):
            with open(path, 'wb') as binary:
                binary.write(content)
        else:
            with open(path, 'w', encoding='utf-8', newline='') as text:
                text.write(content)
        return path

    def parse(self, content: str | bytes) -> Config_Map:
        """Parse ``content`` and return the configuration."""
        return input_parsing(self.write(content))

    def parse_error(
        self, content: str | bytes, line: int | None, *fragments: str
    ) -> str:
        """Assert the parser aborts cleanly and return its error message.

        Checks exit code 1, no traceback, the reported line number
        (unless ``line`` is None) and that every fragment is mentioned.
        """
        stderr = io.StringIO()
        path = self.write(content)
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                input_parsing(path)
        self.assertEqual(raised.exception.code, 1)
        message = stderr.getvalue()
        self.assertNotIn('Traceback', message)
        if line is not None:
            self.assertIn(f"map.txt:{line}:", message)
        for fragment in fragments:
            self.assertIn(fragment, message)
        return message


class ValidInputTests(ParserTestCase):
    """Inputs that must be accepted."""

    def test_minimal_map(self) -> None:
        """A minimal map is parsed into typed zones and connections."""
        config = self.parse(BASE)
        assert config.zones is not None and config.connections is not None
        self.assertEqual(config.nb_drones, 2)
        self.assertEqual((config.start, config.end), ('s', 'g'))
        self.assertEqual([z.name for z in config.zones], ['s', 'a', 'g'])
        self.assertEqual(
            [(c.zone_a, c.zone_b) for c in config.connections],
            [('s', 'a'), ('a', 'g')]
        )

    def test_defaults(self) -> None:
        """Missing metadata falls back to the documented defaults."""
        config = self.parse(BASE)
        assert config.zones is not None and config.connections is not None
        zone = config.zones[1]
        self.assertEqual(zone.zone, zone_types.normal)
        self.assertIsNone(zone.max_drones)
        self.assertIsNone(config.connections[0].max_link_capacity)

    def test_all_zone_types(self) -> None:
        """normal, blocked, restricted and priority are all accepted."""
        for kind in ('normal', 'blocked', 'restricted', 'priority'):
            with self.subTest(kind=kind):
                config = self.parse(
                    edit('hub: a 1 0', f'hub: a 1 0 [zone={kind}]')
                )
                assert config.zones is not None
                self.assertEqual(config.zones[1].zone.value, kind)

    def test_metadata_in_any_order(self) -> None:
        """Metadata tags may appear in any order."""
        for meta in (
            '[zone=priority color=blue max_drones=3]',
            '[max_drones=3 zone=priority color=blue]',
            '[color=blue max_drones=3 zone=priority]',
        ):
            with self.subTest(meta=meta):
                config = self.parse(edit('hub: a 1 0', f'hub: a 1 0 {meta}'))
                assert config.zones is not None
                zone = config.zones[1]
                self.assertEqual(
                    (zone.zone, zone.color, zone.max_drones),
                    (zone_types.priority, 'blue', 3)
                )

    def test_connection_capacity(self) -> None:
        """max_link_capacity is parsed on connections."""
        config = self.parse(
            edit('connection: s-a', 'connection: s-a [max_link_capacity=3]')
        )
        assert config.connections is not None
        self.assertEqual(config.connections[0].max_link_capacity, 3)

    def test_comments_and_empty_lines_are_ignored(self) -> None:
        """Lines starting with # and empty lines are skipped."""
        text = '# header\n\n' + BASE.replace(
            'hub: a', '# a comment\n\nhub: a'
        ) + '# footer\n'
        self.assertEqual(self.parse(text).nb_drones, 2)

    def test_comment_before_nb_drones(self) -> None:
        """Comments may precede the nb_drones line."""
        self.assertEqual(self.parse('# c\n# d\n' + BASE).nb_drones, 2)

    def test_windows_line_endings(self) -> None:
        """CRLF line endings are accepted."""
        self.assertEqual(self.parse(BASE.replace('\n', '\r\n')).nb_drones, 2)

    def test_no_trailing_newline(self) -> None:
        """A missing final newline is fine."""
        self.assertEqual(self.parse(BASE.rstrip('\n')).nb_drones, 2)

    def test_no_space_after_colon(self) -> None:
        """The space after the colon is optional."""
        self.assertEqual(self.parse(BASE.replace(': ', ':')).nb_drones, 2)

    def test_negative_coordinates(self) -> None:
        """Coordinates may be negative integers."""
        config = self.parse(edit('hub: a 1 0', 'hub: a -1 -5'))
        assert config.zones is not None
        self.assertEqual(config.zones[1].coordinates, (-1, -5))

    def test_very_high_capacities(self) -> None:
        """Very large capacities are valid positive integers."""
        huge = 10 ** 9
        config = self.parse(edit(
            'hub: a 1 0', f'hub: a 1 0 [max_drones={huge}]'
        ).replace(
            'connection: s-a', f'connection: s-a [max_link_capacity={huge}]'
        ))
        assert config.zones is not None and config.connections is not None
        self.assertEqual(config.zones[1].max_drones, huge)
        self.assertEqual(config.connections[0].max_link_capacity, huge)

    def test_any_number_of_drones(self) -> None:
        """There is no upper limit on the number of drones."""
        for count in (1, 9999, 10000, 100000):
            with self.subTest(count=count):
                config = self.parse(
                    edit('nb_drones: 2', f'nb_drones: {count}')
                )
                self.assertEqual(config.nb_drones, count)

    def test_unicode_zone_name(self) -> None:
        """Zone names may contain any characters except dashes and spaces."""
        text = (
            "nb_drones: 1\nstart_hub: s 0 0\nhub: \u00e4_zone 1 0\n"
            "end_hub: g 2 0\nconnection: s-\u00e4_zone\n"
            "connection: \u00e4_zone-g\n"
        )
        config = self.parse(text)
        assert config.zones is not None
        self.assertIn('\u00e4_zone', [z.name for z in config.zones])

    def test_start_capacity_may_equal_drone_count(self) -> None:
        """A start zone with max_drones == nb_drones is accepted."""
        config = self.parse(edit(
            'start_hub: s 0 0 [color=green]', 'start_hub: s 0 0 [max_drones=2]'
        ))
        self.assertEqual(config.nb_drones, 2)

    def test_all_provided_maps_parse(self) -> None:
        """Every bundled valid map is parsed without error."""
        root = str(_project.MAPS)
        maps = [
            m for m in glob.glob(
                os.path.join(root, '**', '*.txt'), recursive=True
            ) if os.sep + 'invalid' + os.sep not in m
        ]
        if not maps:
            self.skipTest('no bundled maps found')
        for path in maps:
            with self.subTest(map=os.path.relpath(path, root)):
                self.assertIsNotNone(input_parsing(path).nb_drones)


class NumberOfDronesErrorTests(ParserTestCase):
    """Errors concerning nb_drones."""

    def test_invalid_values(self) -> None:
        """Zero, negative and non-integer values are rejected."""
        cases = {
            '0': 'positive integer', '-3': 'positive integer',
            'abc': 'should be int', '1.5': 'should be int',
            '': 'should be int',
        }
        for value, cause in cases.items():
            with self.subTest(value=value):
                self.parse_error(
                    edit('nb_drones: 2', f'nb_drones: {value}'), 1, cause
                )

    def test_defined_twice(self) -> None:
        """nb_drones may only be defined once (error on the second line)."""
        self.parse_error(BASE + 'nb_drones: 3\n', 7, 'defined once')

    def test_missing(self) -> None:
        """A map without nb_drones is rejected."""
        self.parse_error(BASE.replace('nb_drones: 2\n', ''), 1, 'nb_drones')

    def test_must_be_first_line(self) -> None:
        """nb_drones anywhere but the first line is rejected."""
        text = BASE.replace('nb_drones: 2\n', '') + 'nb_drones: 2\n'
        self.parse_error(text, 1, 'first line must define nb_drones')

    def test_empty_and_comment_only_files(self) -> None:
        """Files without any content are rejected."""
        self.parse_error('', 1, 'Missing parameter: nb_drones')
        self.parse_error('# only\n# comments\n', 1, 'nb_drones')


class HubDefinitionErrorTests(ParserTestCase):
    """Errors in start_hub, end_hub and hub lines."""

    def test_missing_start_or_end(self) -> None:
        """Both start_hub and end_hub are required."""
        self.parse_error(
            edit('start_hub: s 0 0 [color=green]', 'hub: s 0 0'),
            None, 'Missing parameter: start_hub'
        )
        self.parse_error(
            edit('end_hub: g 2 0 [color=red]', 'hub: g 2 0'),
            None, 'Missing parameter: end_hub'
        )

    def test_start_or_end_defined_twice(self) -> None:
        """Exactly one start_hub and one end_hub are allowed."""
        self.parse_error(BASE + 'start_hub: x 5 5\n', 7, 'defined once')
        self.parse_error(BASE + 'end_hub: x 5 5\n', 7, 'defined once')

    def test_invalid_zone_type(self) -> None:
        """Unknown (or wrongly cased, or empty) zone types name the cause."""
        for kind in ('lava', 'Normal', ''):
            with self.subTest(kind=kind):
                self.parse_error(
                    edit('hub: a 1 0', f'hub: a 1 0 [zone={kind}]'), 3,
                    '"zone"',
                    "'normal', 'blocked', 'restricted' or 'priority'",
                    f"got '{kind}'"
                )

    def test_invalid_max_drones(self) -> None:
        """Non-positive or non-integer max_drones are rejected."""
        for value in ('0', '-2', 'abc', '1.5'):
            with self.subTest(value=value):
                self.parse_error(
                    edit('hub: a 1 0', f'hub: a 1 0 [max_drones={value}]'), 3,
                    '"max_drones"', f"got '{value}'"
                )

    def test_invalid_coordinates(self) -> None:
        """Non-integer or missing coordinates are rejected."""
        for coords in ('1.5 0', 'x y', '1 y'):
            with self.subTest(coords=coords):
                self.parse_error(
                    edit('hub: a 1 0', f'hub: a {coords}'), 3, '"coordinates"'
                )
        for definition in ('hub: a', 'hub: a 1'):
            with self.subTest(definition=definition):
                self.parse_error(
                    edit('hub: a 1 0', definition), 3,
                    'expected <name> <x> <y>'
                )

    def test_dash_in_zone_name(self) -> None:
        """Dashes in zone names are reported at the zone's own line."""
        self.parse_error(
            edit('hub: a 1 0', 'hub: a-b 1 0'), 3, 'must not contain dashes'
        )

    def test_duplicate_zone_names(self) -> None:
        """Duplicate names, also with start/end hubs, name the first line."""
        self.parse_error(
            edit('hub: a 1 0', 'hub: a 1 0\nhub: a 5 5'), 4,
            'Zone "a" is already defined on line 3'
        )
        self.parse_error(
            edit('hub: a 1 0', 'hub: s 1 0'), 3,
            'Zone "s" is already defined on line 2'
        )

    def test_start_capacity_below_drone_count(self) -> None:
        """A start zone that cannot hold all drones is rejected."""
        self.parse_error(
            edit(
                'start_hub: s 0 0 [color=green]',
                'start_hub: s 0 0 [max_drones=1]'
            ),
            2, 'max_drones=1', 'nb_drones=2'
        )


class MetadataAndSyntaxErrorTests(ParserTestCase):
    """Errors in the metadata blocks and general line syntax."""

    def test_unknown_lines(self) -> None:
        """Unknown keys and lines without a colon are rejected."""
        self.parse_error(BASE + 'foo: bar\n', 7, 'Invalid Argument', 'foo')
        self.parse_error(BASE + 'this is garbage\n', 7, 'Malformed Line')

    def test_unknown_zone_metadata_key(self) -> None:
        """Unknown zone metadata keys list the allowed ones."""
        self.parse_error(
            edit('hub: a 1 0', 'hub: a 1 0 [speed=3]'), 3,
            '"speed"', 'zone, color, max_drones'
        )

    def test_metadata_without_equals(self) -> None:
        """Metadata that is not key=value is rejected."""
        self.parse_error(
            edit('hub: a 1 0', 'hub: a 1 0 [zone]'), 3, 'expected key=value'
        )

    def test_spaces_around_equals(self) -> None:
        """key = value with spaces is not valid metadata."""
        self.parse_error(
            edit('hub: a 1 0', 'hub: a 1 0 [zone = normal]'), 3,
            'Invalid metadata'
        )

    def test_unknown_connection_metadata_key(self) -> None:
        """Only max_link_capacity is valid on connections."""
        self.parse_error(
            edit('connection: s-a', 'connection: s-a [foo=1]'), 5,
            '"foo"', 'max_link_capacity'
        )


class ConnectionErrorTests(ParserTestCase):
    """Errors in connection lines."""

    def test_invalid_link_capacity(self) -> None:
        """Non-positive or non-integer max_link_capacity are rejected."""
        for value in ('0', '-1', 'x'):
            with self.subTest(value=value):
                self.parse_error(
                    edit(
                        'connection: s-a',
                        f'connection: s-a [max_link_capacity={value}]'
                    ), 5, '"max_link_capacity"', f"got '{value}'"
                )

    def test_duplicate_connections(self) -> None:
        """a-b and b-a are duplicates and name the first definition."""
        self.parse_error(
            BASE + 'connection: s-a\n', 7,
            'Connection "s-a" is already defined on line 5'
        )
        self.parse_error(
            BASE + 'connection: a-s\n', 7,
            'Connection "a-s" is already defined on line 5'
        )

    def test_self_connection(self) -> None:
        """A zone cannot be connected to itself."""
        self.parse_error(
            BASE + 'connection: a-a\n', 7, 'links a zone to itself'
        )

    def test_undefined_zone(self) -> None:
        """Connections may only use defined zones."""
        self.parse_error(
            BASE + 'connection: a-zzz\n', 7, 'undefined zone "zzz"'
        )

    def test_zone_used_before_definition(self) -> None:
        """Connections may only use previously defined zones."""
        text = (
            "nb_drones: 2\nstart_hub: s 0 0\nconnection: s-a\n"
            "hub: a 1 0\nend_hub: g 2 0\nconnection: a-g\n"
        )
        self.parse_error(text, 3, 'zone "a" before it is defined (line 4)')

    def test_malformed_connection_syntax(self) -> None:
        """Connections need exactly <zone1>-<zone2>."""
        for raw in ('sa', 's-a-g', '', 's-', '-a'):
            with self.subTest(raw=raw):
                self.parse_error(
                    BASE + f'connection: {raw}\n', 7,
                    'expected <zone1>-<zone2>'
                )


class MetadataBracketTests(ParserTestCase):
    """The [key=value ...] block: brackets, duplicates and spacing."""

    ZONE = 'hub: a 1 0'
    LINK = 'connection: s-a'

    def zone_error(self, definition: str, *fragments: str) -> None:
        """Assert that a zone definition on line 3 is rejected."""
        self.parse_error(edit(self.ZONE, definition), 3, *fragments)

    def link_error(self, definition: str, *fragments: str) -> None:
        """Assert that a connection definition on line 5 is rejected."""
        self.parse_error(edit(self.LINK, definition), 5, *fragments)

    def test_accepted_forms(self) -> None:
        """Empty block, extra spaces and tabs are fine."""
        for definition in (
            'hub: a 1 0 []',
            'hub: a 1 0 [  zone=priority    max_drones=2  ]',
            'hub: a 1 0 [zone=priority max_drones=2]   ',
            'hub:\ta\t1  0 [zone=priority max_drones=2]',
        ):
            with self.subTest(definition=definition):
                config = self.parse(edit(self.ZONE, definition))
                assert config.zones is not None
                self.assertEqual(config.zones[1].name, 'a')
        config = self.parse(edit(self.ZONE, 'hub: a 1 0 [zone=priority]'))
        assert config.zones is not None
        self.assertEqual(config.zones[1].zone, zone_types.priority)

    def test_unclosed_bracket(self) -> None:
        """A missing ] is reported."""
        self.zone_error('hub: a 1 0 [zone=normal', "missing ']'")

    def test_closing_bracket_without_opening(self) -> None:
        """A ] without [ is reported."""
        self.zone_error('hub: a 1 0 zone=normal]', "without a matching '['")
        self.zone_error('hub: a 1 0 ] zone=normal [', "before '['")

    def test_metadata_needs_brackets(self) -> None:
        """key=value outside of brackets is rejected."""
        self.zone_error(
            'hub: a 1 0 zone=normal', 'zone=normal', 'enclosed in [ ]'
        )

    def test_only_one_block(self) -> None:
        """Two blocks, or nested brackets, are rejected."""
        for definition in (
            'hub: a 1 0 [zone=normal] [color=red]',
            'hub: a 1 0 [[zone=normal]]',
        ):
            with self.subTest(definition=definition):
                self.zone_error(definition, 'Only one metadata block')

    def test_text_after_the_block(self) -> None:
        """Nothing may follow the closing bracket."""
        self.zone_error('hub: a 1 0 [zone=normal] extra', 'after ]', 'extra')

    def test_extra_text_before_the_block(self) -> None:
        """Extra fields (for example an inline comment) are rejected."""
        self.zone_error('hub: a 1 0 # note', 'Unexpected text "# note"')

    def test_duplicate_key(self) -> None:
        """A key may appear only once, in zones and in connections."""
        self.zone_error(
            'hub: a 1 0 [zone=normal zone=blocked]', '"zone" is given twice'
        )
        self.link_error(
            'connection: s-a [max_link_capacity=2 max_link_capacity=3]',
            '"max_link_capacity" is given twice'
        )

    def test_malformed_pairs(self) -> None:
        """Empty keys, several = signs and missing = are rejected."""
        for pair in ('=normal', 'zone=a=b', 'zone', 'zone=normal='):
            with self.subTest(pair=pair):
                self.zone_error(
                    f'hub: a 1 0 [{pair}]', f'Invalid metadata "{pair}"'
                )

    def test_connection_brackets(self) -> None:
        """The same bracket rules apply to connections."""
        self.link_error(
            'connection: s-a [max_link_capacity=2', "missing ']'"
        )
        self.link_error(
            'connection: s-a [max_link_capacity=2] [max_link_capacity=3]',
            'Only one metadata block'
        )
        self.link_error(
            'connection: s-a max_link_capacity=2', 'enclosed in [ ]'
        )

    def test_start_and_end_hub_brackets(self) -> None:
        """The rules also apply to start_hub and end_hub lines."""
        self.parse_error(
            edit('start_hub: s 0 0 [color=green]',
                 'start_hub: s 0 0 [color=green'), 2, "missing ']'"
        )
        self.parse_error(
            edit('end_hub: g 2 0 [color=red]',
                 'end_hub: g 2 0 [color=red] [zone=normal]'), 4,
            'Only one metadata block'
        )


class FileErrorTests(ParserTestCase):
    """Problems with the file itself must not crash the program."""

    def test_missing_file(self) -> None:
        """A nonexistent path exits with status 1."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                input_parsing(os.path.join(self._tmp.name, 'nope.txt'))
        self.assertEqual(raised.exception.code, 1)
        self.assertNotIn('Traceback', stderr.getvalue())

    def test_directory_instead_of_file(self) -> None:
        """A directory path exits with status 1."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as raised:
                input_parsing(self._tmp.name)
        self.assertEqual(raised.exception.code, 1)

    def test_binary_garbage(self) -> None:
        """Non-text content exits with status 1 instead of a traceback."""
        self.parse_error(bytes(range(256)), None)


if __name__ == '__main__':
    unittest.main()
