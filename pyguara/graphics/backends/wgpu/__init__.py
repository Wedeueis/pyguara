"""The wgpu rendering backend: one native renderer for every platform.

Selected with `display.backend = "wgpu"`. See
`project/backlog/active/next_engine_plan.md` for the stages; this is
stage A.
"""

from pyguara.graphics.backends.wgpu.frame import GpuFrame
from pyguara.graphics.backends.wgpu.renderer import WgpuRenderer
from pyguara.graphics.backends.wgpu.ui_renderer import WgpuUIRenderer
from pyguara.graphics.backends.wgpu.window import WgpuWindow

__all__ = ["GpuFrame", "WgpuRenderer", "WgpuUIRenderer", "WgpuWindow"]
