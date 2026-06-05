#!/usr/bin/env python3
"""Run isolated BTC high-win candidate wallet observation.

Simulation only. This wrapper intentionally shares the paper-trading simulator
but writes to its own logs and is not consumed by the live execution router.
"""

from __future__ import annotations

import btc_directional_wallet_copy_sim as simulator


if __name__ == "__main__":
    raise SystemExit(simulator.main())
