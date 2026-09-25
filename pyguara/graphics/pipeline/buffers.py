"""The standard framebuffer chain, and the format it carries.

A frame moves through four named buffers -- world, lightmap, composite,
post-processed -- and until now nothing owned their format. Each was created
by whichever pass reached it first, at the manager's 8-bit default, while the
light map was widened to 16-bit float by each demo's bootstrap doing it by
hand before `LightPass` could claim it. The extra range died at the composite,
and `bloom_composite.frag`'s tonemap was commented out to match.

This module is where the chain is described instead: the names, and the format
they carry. `RenderGraph` declares them on the manager at construction, and the
effects that own their own scratch buffers declare theirs the same way, so a
pass downstream asks for a buffer by name and gets the format the chain says it
has rather than whatever the first caller happened to want.
"""

from __future__ import annotations

WORLD_FBO_NAME = "world"
LIGHT_FBO_NAME = "lightmap"
COMPOSITE_FBO_NAME = "composite"
POST_PROCESSED_FBO_NAME = "post_processed"

HDR_DTYPE = "f2"
"""16-bit float, so a value above 1.0 survives to be tonemapped.

`bloom_composite.frag` is where it is tonemapped: a knee at 0.8, identity
below and asymptotic to 1.0 above. That choice is what let the range be
brought in without re-tuning the demos lit against the old clamped
pipeline -- a plain Reinhard maps the whole scale, and would have pulled
every mid-tone in `tamandua_murundus` and `mourisco_ressonancia` down with
it. See `tests/integration/test_bloom_tonemap_pixels.py`.
"""

STANDARD_CHAIN: tuple[str, ...] = (
    WORLD_FBO_NAME,
    LIGHT_FBO_NAME,
    COMPOSITE_FBO_NAME,
    POST_PROCESSED_FBO_NAME,
)
"""The buffers `RenderGraph` declares as HDR when it is constructed."""
