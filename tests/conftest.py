from __future__ import annotations

from pathlib import Path

import pytest
from kohra.scenario.load import load_scenario, resolve_path
from kohra.scenario.schema import Scenario
from kohra.sim.world import World, build_world
from pyproj import Transformer

from tests.fixtures.dems import flat_for_bbox

ROOT = Path(__file__).resolve().parents[1]
RIDGE = ROOT / "scenarios" / "ridge.yaml"
BOT = ROOT / "scenarios" / "ridge.bot.yaml"
DEMO_INJECTS = ROOT / "scenarios" / "demo_injects.yaml"
ALL_INJECTS = ROOT / "tests" / "fixtures" / "all_injects.yaml"


@pytest.fixture(scope="session")
def ridge() -> tuple[Scenario, str]:
    return load_scenario(RIDGE)


def flat_world(scen: Scenario) -> World:
    fwd = Transformer.from_crs("EPSG:4326", scen.terrain.crs_sim, always_xy=True)
    b = scen.terrain.bbox
    xs, ys = fwd.transform([b[0], b[2]], [b[1], b[3]])
    return build_world(scen, flat_for_bbox((xs[0], ys[0], xs[1], ys[1])))


@pytest.fixture(scope="session")
def flat_ridge_world(ridge: tuple[Scenario, str]) -> World:
    return flat_world(ridge[0])


@pytest.fixture(scope="session")
def terrain_available(ridge: tuple[Scenario, str]) -> bool:
    if not resolve_path(ridge[0].terrain.terrain_file).exists():
        pytest.skip("no data/terrain/terrain.npz: run scripts/synth_terrain.py or build_terrain.py")
    return True
