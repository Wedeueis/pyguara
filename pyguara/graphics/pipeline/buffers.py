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

Nothing in the chain produces one yet except the light map -- re-enabling the
Reinhard tonemap in `bloom_composite.frag`, and re-tuning the demos that were
lit against a clamped pipeline, is deliberately a separate change.
"""

STANDARD_CHAIN: tuple[str, ...] = (
    WORLD_FBO_NAME,
    LIGHT_FBO_NAME,
    COMPOSITE_FBO_NAME,
    POST_PROCESSED_FBO_NAME,
)
"""The buffers `RenderGraph` declares as HDR when it is constructed."""
