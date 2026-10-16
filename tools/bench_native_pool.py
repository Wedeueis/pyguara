#!/usr/bin/env python3
"""Marco 3's number: a native SoA particle pool against the Python one.

RFC-0003's Marco 3 replaces `ParticleSystem`, `Sparks` and
`ProjectileSystem` with native structure-of-arrays pools and claims ~45x.
This measures one of them -- particles -- because one real number decides
the milestone. See `docs/adr/0003-native-core-spike.md`.

Needs the spike crate built first, which needs a Rust toolchain:

    cargo build --release
    uv run python tools/bench_native_pool.py

The crate is deliberately not wired into `pyproject.toml`, so `uv sync`
keeps working without Rust; this loads the compiled library straight from
`target/release/`.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import timeit
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from pyguara.common.types import Vector2  # noqa: E402
from pyguara.graphics.components.particles import ParticleSystem  # noqa: E402

DT = 1.0 / 60.0
LIFE = 1e6  # outlive the measurement


class _FakeTexture:
    """A texture the pool can hold without a GL context."""

    @property
    def width(self) -> int:
        """Width in pixels."""
        return 8

    @property
    def height(self) -> int:
        """Height in pixels."""
        return 8

    @property
    def native_handle(self) -> object:
        """Never bound; the pool only stores it."""
        return self


def _load_native() -> object | None:
    """Import the spike crate's compiled library, or None if unbuilt."""
    library = _ROOT / "target" / "release" / "libpyguara_core_rs.so"
    if not library.exists():
        return None
    spec = importlib.util.spec_from_file_location("pyguara_core_rs", library)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _python_pool(capacity: int, live: int) -> ParticleSystem:
    """A Python pool with `live` slots occupied."""
    system = ParticleSystem(capacity=capacity)
    if live:
        system.emit(
            _FakeTexture(),  # type: ignore[arg-type]
            Vector2(0.0, 0.0),
            count=live,
            speed=100.0,
            spread=0.0,
            life=LIFE,
        )
    return system


def _ms(fn: object, number: int = 200, repeat: int = 5) -> float:
    """Fastest run in milliseconds."""
    return min(timeit.repeat(fn, number=number, repeat=repeat)) / number * 1e3  # type: ignore[arg-type]


def main() -> int:
    """Check parity, then compare update cost.

    Returns:
        0 on success, 1 if the crate is not built.
    """
    native = _load_native()
    if native is None:
        print("spike crate not built -- run `cargo build --release` first")
        return 1

    # Parity on identical initial state. `ParticleSystem.emit` randomises
    # speed over [speed*0.5, speed*1.5], so the two pools cannot be seeded
    # through their own emit paths and compared.
    python_pool = _python_pool(16, 1)
    seeded = next(p for p in python_pool._pool if p.active)
    seeded.position = Vector2(0.0, 0.0)
    seeded.velocity = Vector2(100.0, 0.0)
    seeded.acceleration = Vector2(0.0, 0.0)
    seeded.damping = 1.0
    seeded.life = LIFE

    rust_pool = native.NativeParticlePool(16)  # type: ignore[attr-defined]
    rust_pool.emit(1, 0.0, 0.0, 100.0, 0.0, LIFE)

    for _ in range(60):
        python_pool.update(DT)
        rust_pool.update(DT)

    rust_x, _ = rust_pool.position_at(0)
    drift = abs(seeded.position.x - rust_x)
    print("parity after 60 ticks")
    print(
        f"  python {seeded.position.x:.4f}   rust {rust_x:.4f}   drift {drift:.6f} px"
    )
    print(f"  {'f32 rounding' if drift < 0.01 else 'THE MATHS DISAGREE'}")

    print(f"\n{'scenario':28} {'python ms':>10} {'rust ms':>9} {'speedup':>8}")
    for capacity, live in ((1000, 1000), (4000, 4000), (1000, 0)):
        py_pool = _python_pool(capacity, live)
        rs_pool = native.NativeParticlePool(capacity)  # type: ignore[attr-defined]
        if live:
            rs_pool.emit(live, 0.0, 0.0, 100.0, 0.0, LIFE)
        py_ms = _ms(lambda pool=py_pool: pool.update(DT))
        rs_ms = _ms(lambda pool=rs_pool: pool.update(DT))
        print(
            f"{f'{live} live / {capacity} capacity':28} "
            f"{py_ms:10.3f} {rs_ms:9.3f} {py_ms / rs_ms:7.1f}x"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
