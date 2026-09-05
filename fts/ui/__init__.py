"""GTK4/libadwaita UI for Foot Theme Studio.

Panels:

- :mod:`fts.ui.library_panel`  -- searchable palette library (left pane)
- :mod:`fts.ui.swatches`       -- per-role color tiles (center top)
- :mod:`fts.ui.imagewell`      -- image drop/chooser -> extracted palette
- :mod:`fts.ui.preview`        -- fake terminal preview (center bottom)
- :mod:`fts.ui.colortest_view` -- in-app truecolor spectrum surface
- :mod:`fts.ui.dialogs`        -- save-as-theme + color test dialogs
- :mod:`fts.ui.window`         -- FtsWindow, owns the working palette

Launch with ``python3 -m fts.main`` or the ``bin/foot-theme-studio`` shim.
"""

from __future__ import annotations

__all__ = ["run"]


def run() -> None:
    """Convenience launcher (equivalent to ``python3 -m fts.main``)."""
    from ..main import main

    main()
