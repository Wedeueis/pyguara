"""Test setup for the demos' own tests, shared with the engine's.

Importing the engine's conftest applies its environment (no test opens a
real window) and registers its autouse fixtures here: the UI theme is
restored and leaked GPU devices are freed after each test.
"""

from tests.conftest import _free_leaked_gpu_devices, _restore_ui_theme

__all__ = ["_free_leaked_gpu_devices", "_restore_ui_theme"]
