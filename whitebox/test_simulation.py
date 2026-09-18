"""White-box tests: planning, scheduler, turn log and Pygame view."""

import contextlib
import glob
import io
import os
import tempfile
import unittest

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from . import _project  # noqa: E402
from src.input_parsing import (  # noqa: E402
    Config_Map, input_parsing, zone_types
)
from src.pathfinding_algorithm import CustomException  # noqa: E402
from src.simulation_engine import build_scheduler  # noqa: E402

ROOT = str(_project.ROOT)
MAPS = str(_project.MAPS)

TARGETS = {
    'easy/01_linear_path': 6, 'easy/02_simple_fork': 6,
    'easy/03_basic_capacity': 8, 'medium/01_dead_end_trap': 15,
    'medium/02_circular_loop': 20, 'medium/03_priority_puzzle': 12,
    'hard/01_maze_nightmare': 45, 'hard/02_capacity_hell': 60,
    'hard/03_ultimate_challenge': 35,
}


def check_log(config: Config_Map, log: list[str]) -> list[str]:
    """Validate a turn log against the rules, independent of the engine.

    Returns the list of rule violations (empty if the log is valid).
    """
    assert config.zones is not None and config.connections is not None
    zones = {z.name: z for z in config.zones}
    links = {
        frozenset({c.zone_a, c.zone_b}): c.max_link_capacity or 1
        for c in config.connections
    }
    start, end = config.start, config.end
    assert start is not None and end is not None and config.nb_drones
    position: dict[int, str | None] = {
        i: start for i in range(config.nb_drones)
    }
    transit: dict[int, tuple[frozenset[str], str, int]] = {}
    errors: list[str] = []

    def capacity(zone: str) -> int | None:
        if zone in (start, end):
            return None
        return zones[zone].max_drones or 1

    for turn, line in enumerate(log, 1):
        acted: set[int] = set()
        link_use: dict[frozenset[str], int] = {}
        for token in line.split():
            parts = token.split('-', 2)
            drone = int(parts[0][1:])
            if drone in acted:
                errors.append(f'T{turn}: D{drone} acts twice')
            acted.add(drone)
            if len(parts) == 3:
                source, target = parts[1], parts[2]
                link = frozenset({source, target})
                if position[drone] != source or link not in links:
                    errors.append(f'T{turn}: bad departure {token}')
                    continue
                if zones[target].zone != zone_types.restricted:
                    errors.append(f'T{turn}: {target} is not restricted')
                transit[drone] = (link, target, turn + 1)
                position[drone] = None
                link_use[link] = link_use.get(link, 0) + 1
            elif drone in transit:
                link, target, arrival = transit.pop(drone)
                if parts[1] != target or arrival != turn:
                    errors.append(f'T{turn}: bad landing {token}')
                position[drone] = target
                link_use[link] = link_use.get(link, 0) + 1
            else:
                origin, destination = position[drone], parts[1]
                if origin is None:
                    errors.append(f'T{turn}: {token} while in transit')
                    continue
                link = frozenset({origin, destination})
                if link not in links:
                    errors.append(
                        f'T{turn}: no connection {origin}-{destination}'
                    )
                    continue
                if zones[destination].zone in (
                    zone_types.restricted, zone_types.blocked
                ):
                    errors.append(
                        f'T{turn}: illegal move into {destination}'
                    )
                position[drone] = destination
                link_use[link] = link_use.get(link, 0) + 1
        for drone, (link, target, arrival) in transit.items():
            if arrival <= turn and drone not in acted:
                errors.append(f'T{turn}: D{drone} did not land in time')
        for link, used in link_use.items():
            if used > links[link]:
                errors.append(f'T{turn}: link {sorted(link)} over capacity')
        occupancy: dict[str, int] = {}
        for drone in position:
            zone = position[drone]
            where = zone if zone is not None else transit[drone][1]
            occupancy[where] = occupancy.get(where, 0) + 1
        for zone_name, count in occupancy.items():
            limit = capacity(zone_name)
            if limit is not None and count > limit:
                errors.append(f'T{turn}: zone {zone_name} over capacity')
    for drone, final_zone in position.items():
        if final_zone != end:
            errors.append(f'D{drone} finished at {final_zone}, not {end}')
    return errors


class SimulationTestCase(unittest.TestCase):
    """Helpers to build a scheduler from map text."""

    def setUp(self) -> None:
        """Create a temporary directory for the map files."""
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def config(self, text: str) -> Config_Map:
        """Parse ``text`` as a map file."""
        path = os.path.join(self._tmp.name, 'map.txt')
        with open(path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return input_parsing(path)

    def run_map(self, text: str) -> list[str]:
        """Plan and simulate ``text``; assert the log follows the rules."""
        config = self.config(text)
        log = build_scheduler(config).run()
        self.assertEqual(check_log(config, log), [])
        return log


def chain(drones: int, middle: str = 'hub: a 1 0', links: str = '') -> str:
    """Return the map s - a - g with ``drones`` drones."""
    return (
        f"nb_drones: {drones}\nstart_hub: s 0 0\n{middle}\n"
        f"end_hub: g 2 0\nconnection: s-a {links}\nconnection: a-g {links}\n"
    )


class MovementRuleTests(SimulationTestCase):
    """Zone costs, capacities and the output format."""

    def test_single_drone(self) -> None:
        """One drone on a linear path needs one turn per zone."""
        self.assertEqual(self.run_map(chain(1)), ['D0-a', 'D0-g'])

    def test_default_capacity_is_one(self) -> None:
        """With default capacities two drones must follow each other."""
        self.assertEqual(
            self.run_map(chain(2)), ['D0-a', 'D0-g D1-a', 'D1-g']
        )

    def test_stationary_drones_are_omitted(self) -> None:
        """A drone that waits does not appear in the turn line."""
        first_turn = self.run_map(chain(2))[0]
        self.assertNotIn('D1', first_turn)

    def test_high_capacity_moves_drones_together(self) -> None:
        """Zone and link capacity 2 let two drones move simultaneously."""
        log = self.run_map(chain(
            2, 'hub: a 1 0 [max_drones=2]', '[max_link_capacity=2]'
        ))
        self.assertEqual(log, ['D0-a D1-a', 'D0-g D1-g'])

    def test_zone_capacity_limits_even_with_free_links(self) -> None:
        """A zone with max_drones=1 stays serial despite link capacity 2."""
        log = self.run_map(chain(2, links='[max_link_capacity=2]'))
        self.assertEqual(len(log), 3)

    def test_link_capacity_limits_even_with_free_zones(self) -> None:
        """A zone with max_drones=2 stays serial with link capacity 1."""
        log = self.run_map(chain(2, 'hub: a 1 0 [max_drones=2]'))
        self.assertEqual(len(log), 3)

    def test_start_and_end_are_shared(self) -> None:
        """Many drones share the start and end zones."""
        log = self.run_map(chain(100))
        self.assertEqual(len(log), 101)

    def test_restricted_zone_takes_two_turns(self) -> None:
        """Entering a restricted zone shows the connection first."""
        log = self.run_map(chain(1, 'hub: a 1 0 [zone=restricted]'))
        self.assertEqual(log, ['D0-s-a', 'D0-a', 'D0-g'])

    def test_priority_zone_is_preferred(self) -> None:
        """With equal cost the path through the priority zone wins."""
        text = (
            "nb_drones: 1\nstart_hub: s 0 0\nhub: n 1 0\n"
            "hub: p 1 1 [zone=priority]\nend_hub: g 2 0\n"
            "connection: s-n\nconnection: n-g\nconnection: s-p\n"
            "connection: p-g\n"
        )
        self.assertEqual(self.run_map(text), ['D0-p', 'D0-g'])

    def test_restricted_detour_is_avoided_when_slower(self) -> None:
        """A normal path is chosen over an equally long restricted one."""
        text = (
            "nb_drones: 1\nstart_hub: s 0 0\nhub: n 1 0\n"
            "hub: r 1 1 [zone=restricted]\nend_hub: g 2 0\n"
            "connection: s-n\nconnection: n-g\nconnection: s-r\n"
            "connection: r-g\n"
        )
        self.assertEqual(self.run_map(text), ['D0-n', 'D0-g'])

    def test_log_format(self) -> None:
        """Every token has the form D<id>-<zone> or D<id>-<from>-<to>."""
        log = self.run_map(chain(3, 'hub: a 1 0 [zone=restricted]'))
        for line in log:
            self.assertTrue(line)
            for token in line.split():
                self.assertRegex(token, r'^D\d+-[^\s-]+(-[^\s-]+)?$')

    def test_output_stops_when_all_delivered(self) -> None:
        """The last turn ends with every drone in the end zone."""
        config = self.config(chain(3))
        scheduler = build_scheduler(config)
        log = scheduler.run()
        self.assertEqual(len(log), scheduler.current_turn)
        self.assertEqual(log[-1], 'D2-g')


class BlockedZoneAndPathTests(SimulationTestCase):
    """Blocked zones, unreachable goals and unusable maps."""

    BYPASS = (
        "nb_drones: 2\nstart_hub: s 0 0\nhub: x 1 0 [zone=blocked]\n"
        "hub: w 2 0\nend_hub: g 3 0\nconnection: s-x\nconnection: x-g\n"
        "connection: s-w\nconnection: w-g\n"
    )

    def test_blocked_zone_is_bypassed(self) -> None:
        """Connections to a blocked zone are accepted and routed around."""
        log = self.run_map(self.BYPASS)
        for line in log:
            self.assertNotIn('-x', line)

    def test_isolated_blocked_zone_is_fine(self) -> None:
        """A blocked zone without connections does not matter."""
        self.run_map(chain(1, 'hub: a 1 0\nhub: x 5 5 [zone=blocked]'))

    def test_blocked_zone_as_only_path(self) -> None:
        """If a blocked zone is the only route there is no valid path."""
        with self.assertRaises(CustomException) as raised:
            build_scheduler(self.config(chain(1, 'hub: a 1 0 [zone=blocked]')))
        self.assertIn('No valid path', str(raised.exception))

    def test_blocked_start_or_end(self) -> None:
        """A blocked start or end hub is rejected."""
        for old, new in (
            ('start_hub: s 0 0', 'start_hub: s 0 0 [zone=blocked]'),
            ('end_hub: g 2 0', 'end_hub: g 2 0 [zone=blocked]'),
        ):
            with self.subTest(hub=old):
                with self.assertRaises(CustomException):
                    build_scheduler(self.config(chain(1).replace(old, new)))

    def test_disconnected_graph(self) -> None:
        """A goal that is not connected to the start is reported."""
        text = chain(1).replace('connection: a-g \n', '')
        with self.assertRaises(CustomException) as raised:
            build_scheduler(self.config(text))
        self.assertIn('No valid path', str(raised.exception))

    def test_no_connections_at_all(self) -> None:
        """A map without any connection is reported."""
        text = (
            "nb_drones: 1\nstart_hub: s 0 0\nend_hub: g 2 0\n"
        )
        with self.assertRaises(CustomException):
            build_scheduler(self.config(text))


class ProvidedMapTests(SimulationTestCase):
    """Every bundled map is solved validly; mandatory targets are met."""

    def maps(self) -> list[str]:
        """Return the bundled, valid map files."""
        found = [
            m for m in glob.glob(
                os.path.join(MAPS, '**', '*.txt'), recursive=True
            ) if os.sep + 'invalid' + os.sep not in m
        ]
        if not found:
            self.skipTest('no bundled maps found')
        return found

    def test_every_map_produces_a_valid_log(self) -> None:
        """No map violates capacity, connection or movement rules."""
        for path in self.maps():
            with self.subTest(map=os.path.relpath(path, MAPS)):
                config = input_parsing(path)
                log = build_scheduler(config).run()
                self.assertEqual(check_log(config, log), [])

    def test_reference_targets(self) -> None:
        """Easy, medium and hard maps are solved within the targets."""
        self.maps()
        for name, target in TARGETS.items():
            with self.subTest(map=name):
                config = input_parsing(
                    os.path.join(MAPS, name + '.txt')
                )
                turns = len(build_scheduler(config).run())
                self.assertLessEqual(turns, target)

    def test_invalid_maps_are_rejected_cleanly(self) -> None:
        """Every file in maps/extra/invalid fails with a clean message."""
        invalid = glob.glob(
            os.path.join(MAPS, 'extra', 'invalid', '*.txt')
        )
        if not invalid:
            self.skipTest('no invalid maps found')
        for path in invalid:
            with self.subTest(map=os.path.basename(path)):
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    with self.assertRaises((SystemExit, CustomException)):
                        build_scheduler(input_parsing(path))
                self.assertNotIn('Traceback', stderr.getvalue())


class FreshSchedulerTests(SimulationTestCase):
    """Every simulation starts from a fresh, independent scheduler."""

    def test_schedulers_are_independent(self) -> None:
        """A finished run does not influence a newly built scheduler."""
        config = self.config(chain(3))
        first = build_scheduler(config)
        first_log = first.run()
        second = build_scheduler(config)
        self.assertIsNot(first, second)
        self.assertEqual(second.current_turn, 0)
        self.assertEqual(second.run(), first_log)

    def test_planning_is_deterministic(self) -> None:
        """Building a scheduler twice yields the same turn log."""
        config = self.config(chain(4, 'hub: a 1 0 [max_drones=2]'))
        self.assertEqual(
            build_scheduler(config).run(), build_scheduler(config).run()
        )


try:
    import pygame as pg
    from src.visual_representation import DroneScreen, Visualizer
    HAVE_PYGAME = True
except ImportError:  # pragma: no cover
    HAVE_PYGAME = False


@unittest.skipUnless(HAVE_PYGAME, 'pygame is not installed')
class VisualizerTests(SimulationTestCase):
    """The Pygame drone screen (rendered with a dummy video driver)."""

    screen: 'pg.Surface'

    @classmethod
    def setUpClass(cls) -> None:
        """Start pygame from the project root (assets use relative paths)."""
        previous = os.getcwd()
        os.chdir(ROOT)
        cls.addClassCleanup(os.chdir, previous)
        pg.init()
        cls.addClassCleanup(pg.quit)
        cls.screen = pg.display.set_mode((1920, 1080))

    def visualizer(self, text: str) -> 'Visualizer':
        """Return a Visualizer, with fonts, for the map ``text``."""
        config = self.config(text)
        visualizer = Visualizer(
            config.zones, config.connections, build_scheduler(config)
        )
        visualizer._font_intro = pg.font.Font('src/visual/assets/font.ttf', 42)
        visualizer._font = pg.font.Font('src/visual/assets/font.ttf', 21)
        return visualizer

    def drone_screen(self, visualizer: 'Visualizer') -> 'DroneScreen':
        """Build the drone screen and narrow it to its concrete type."""
        scene = visualizer._make_scene('drone')
        assert isinstance(scene, DroneScreen)
        return scene

    def test_unknown_color_does_not_crash(self) -> None:
        """An unknown color name warns and falls back instead of raising."""
        text = chain(1, 'hub: a 1 0 [color=rainbow]')
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            scene = self.drone_screen(self.visualizer(text))
            scene.update(0.1)
            scene.draw(self.screen)
        self.assertIn("unknown color 'rainbow'", stderr.getvalue())

    def test_known_colors_do_not_warn(self) -> None:
        """Valid color names render without any warning."""
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.drone_screen(
                self.visualizer(chain(1, 'hub: a 1 0 [color=gray]'))
            )
        self.assertEqual(stderr.getvalue(), '')

    def test_reentering_screen_starts_at_turn_zero(self) -> None:
        """A second screen for the same map gets a fresh scheduler."""
        visualizer = self.visualizer(chain(2))
        first = self.drone_screen(visualizer)
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(50):
                first.update(5.0)
        second = self.drone_screen(visualizer)
        self.assertEqual(second.scheduler.current_turn, 0)
        with contextlib.redirect_stdout(io.StringIO()):
            second.update(5.0)
        self.assertEqual(second.scheduler.current_turn, 1)

    def test_retry_restarts_the_simulation(self) -> None:
        """The R key and the button restart from turn 0."""
        visualizer = self.visualizer(chain(2))
        scene = self.drone_screen(visualizer)
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(50):
                scene.update(5.0)
        self.assertTrue(scene._finished)
        scene.handle_event(pg.event.Event(pg.KEYDOWN, key=pg.K_r))
        self.assertEqual(scene.scheduler.current_turn, 0)
        self.assertFalse(scene._finished)
        with contextlib.redirect_stdout(io.StringIO()):
            for _ in range(50):
                scene.update(5.0)
        self.assertTrue(scene._finished)
        click = pg.event.Event(
            pg.MOUSEBUTTONDOWN, pos=scene._retry_rect.center, button=1
        )
        scene.handle_event(click)
        self.assertEqual(scene.scheduler.current_turn, 0)


if __name__ == '__main__':
    unittest.main()
