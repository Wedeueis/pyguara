"""The standard framebuffer chain, and the format it carries.

A frame moves through four named buffers: world, lightmap, composite
and post-processed. This module names them and the format each has.
`RenderGraph` declares them on the manager at construction, and
effects with their own scratch buffers declare theirs the same way, so
a pass asking for a buffer by name gets the declared format.
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
