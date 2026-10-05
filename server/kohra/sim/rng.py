"""Named, independent random streams (D9). Add new streams only at the END of STREAMS."""

from __future__ import annotations

from typing import Any

import numpy as np

STREAMS: tuple[str, ...] = ("move", "detect", "reports", "comms", "burst", "outcome", "gnss", "ids", "scripts")


class Rng:
    """Bundle of one PCG64 generator per subsystem: stream i = PCG64(SeedSequence(seed, spawn_key=(i,)))."""

    def __init__(self, seed: int) -> None:
        self.seed = int(seed)
        self.gens: dict[str, np.random.Generator] = {
            name: np.random.Generator(np.random.PCG64(np.random.SeedSequence(entropy=self.seed, spawn_key=(i,))))
            for i, name in enumerate(STREAMS)
        }

    def __getattr__(self, name: str) -> np.random.Generator:
        gens: dict[str, np.random.Generator] = self.__dict__["gens"]
        try:
            return gens[name]
        except KeyError as e:
            raise AttributeError(name) from e

    def state(self) -> dict[str, Any]:
        return {name: self.gens[name].bit_generator.state for name in STREAMS}
