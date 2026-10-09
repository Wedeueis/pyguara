"""Entry point for `python -m pyguara.cli`.

The `if __name__ == "__main__"` block in `__init__.py` cannot fire: inside
a package's `__init__`, `__name__` is `pyguara.cli`, never `__main__`. So
`python -m pyguara.cli` failed with "cannot be directly executed" and the
only way in was the installed `pyguara` console script -- which a test, a
CI step or a freshly cloned checkout may not have on its PATH.
"""

from pyguara.cli import main

if __name__ == "__main__":
    main()
