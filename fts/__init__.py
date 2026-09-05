"""Terminal Theme Studio core (non-GUI) logic.

Author, preview, and apply terminal palettes to Foot on Omarchy:

- ``fts.paths``        -- path indirection (testable via FOOT_THEME_STUDIO_HOME)
- ``fts.palette``      -- Palette model + color math
- ``fts.omarchy``      -- colors.toml read/write, user themes, full theme apply
- ``fts.foot_config``  -- palette.ini + foot.ini include management
- ``fts.osc``          -- OSC sequence building + push to running Foot
- ``fts.library``      -- bundled + local theme library with search
- ``fts.quantize``     -- median-cut extraction + palette mapping
- ``fts.colortest``    -- text/ANSI test generators

Only ``fts.quantize.extract_palette`` may touch GdkPixbuf (lazily); every
module imports without a display.
"""

__version__ = "0.1.0"
