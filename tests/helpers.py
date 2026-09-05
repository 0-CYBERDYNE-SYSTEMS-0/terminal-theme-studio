"""Shared test helpers.

Tests NEVER touch the real ~/.config/foot, ~/.config/omarchy or /dev/pts:
``EnvHomeTestCase`` redirects FOOT_THEME_STUDIO_HOME (and OMARCHY_PATH)
to a fresh tempfile.mkdtemp and restores the environment afterwards.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest


class EnvHomeTestCase(unittest.TestCase):
    """Redirect all user/system config paths to a throwaway tmpdir."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp(prefix="fts-test-")
        self._saved: dict[str, str | None] = {}
        for var in ("FOOT_THEME_STUDIO_HOME", "OMARCHY_PATH"):
            self._saved[var] = os.environ.get(var)
        os.environ["FOOT_THEME_STUDIO_HOME"] = self.tmpdir
        os.environ["OMARCHY_PATH"] = os.path.join(self.tmpdir, "omarchy-fake")
        self.addCleanup(self._restore_env)
        self.addCleanup(
            lambda: shutil.rmtree(self.tmpdir, ignore_errors=True)
        )

    def _restore_env(self) -> None:
        for var, old in self._saved.items():
            if old is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = old
