#!/usr/bin/env python3
"""Run the real Gio resource transform against signed, stock Arch Shell assets."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HELPER = Path(__file__).resolve().parents[1] / "device_files/mipad2-gnome-osk-patch"
loader = importlib.machinery.SourceFileLoader("mipad2_osk", str(HELPER))
module = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(module)
FIXTURE = os.environ.get("MIPAD2_GNOME51_STOCK")


class Profile(unittest.TestCase):
    def test_only_qualified_51_package_and_legacy_50_profile(self):
        self.assertEqual(module.profile("GNOME Shell 50.2", "1:50.2-1"), {})
        self.assertEqual(module.profile("GNOME Shell 51.1", "1:51.1-1"), module.ARCH_51_1)
        self.assertIsNone(module.profile("GNOME Shell 51.1", "1:51.1-2"))
        self.assertIsNone(module.profile("GNOME Shell 51.2", "1:51.2-1"))
        self.assertIsNone(module.profile("GNOME Shell 52.0", "1:52.0-1"))
        with self.assertRaises(ValueError):
            module.profile("GNOME Shell 51.1", "../../mistake")


@unittest.skipUnless(FIXTURE, "verified GNOME 51 fixture directory required")
class RealStock(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="mipad2-gnome51-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.shell = self.root / "gnome-shell"
        self.shell.mkdir()
        self.backups = self.root / "backups"
        for name in (module.LAYOUT, module.THEME):
            shutil.copyfile(Path(FIXTURE) / name, self.shell / name)

    def call(self, verify=False, shell="GNOME Shell 51.1", pkgver="1:51.1-1"):
        return module.apply(self.shell, self.backups, shell, pkgver, verify_only=verify)

    def data(self):
        return {p.name: p.read_bytes() for p in self.shell.iterdir()}

    def test_real_resources_preserve_all_non_keyboard_bytes_and_content(self):
        stable = {q: module.read_resources(self.shell / q) for q in (module.LAYOUT, module.THEME)}
        self.assertTrue(self.call())
        self.assertTrue(self.call(verify=True))
        new = {q: module.read_resources(self.shell / q) for q in stable}
        for name, want in [
            (module.LAYOUT, {module.LAYOUT_PREFIX + x for x in ("us.json", "us-extended.json")}),
            (module.THEME, {module.THEME_PREFIX + x for x in module.CSS_NAMES}),
        ]:
            self.assertEqual(set(stable[name]), set(new[name]))
            self.assertEqual({k for k, v in stable[name].items() if new[name][k] != v}, want)
        key = module.LAYOUT_PREFIX + "us-extended.json"
        original = json.loads(stable[module.LAYOUT][key])["levels"]
        actual = json.loads(new[module.LAYOUT][key])["levels"]
        self.assertEqual([x["level"] for x in actual], [x["level"] for x in original])
        for stock, out in zip(original, actual, strict=True):
            if out["level"] in ("default", "shift"):
                self.assertEqual(len(out["rows"]), 4)
            for a, b in zip(stock["rows"], out["rows"], strict=True):
                for old_key, new_key in zip(a, b, strict=True):
                    self.assertEqual(new_key["width"], 2 * old_key.get("width", 1))
                    if "leftOffset" in old_key:
                        self.assertEqual(new_key["leftOffset"], 2 * old_key["leftOffset"])
                    self.assertEqual({x: y for x, y in old_key.items() if x not in {"width", "leftOffset"}},
                                     {x: y for x, y in new_key.items() if x not in {"width", "leftOffset"}})
        for css in module.CSS_NAMES:
            k = module.THEME_PREFIX + css
            self.assertEqual(new[module.THEME][k], stable[module.THEME][k] + module.CSS_PATCH)

    def test_verify_is_readonly_and_reapply_is_idempotent(self):
        stock = self.data()
        with self.assertRaises(ValueError):
            self.call(verify=True)
        self.assertFalse(self.backups.exists())
        self.assertEqual(self.data(), stock)
        self.call()
        compact = self.data()
        self.call()
        self.assertEqual(self.data(), compact)
        for name in stock:
            self.assertEqual((self.backups / f"{name}.1:51.1-1.stock").read_bytes(), stock[name])

    def test_mismatch_fails_closed_and_unknown_future_release_is_untouched(self):
        stock = self.data()
        self.assertFalse(self.call(shell="GNOME Shell 51.2", pkgver="1:51.2-1"))
        self.assertFalse(self.backups.exists())
        self.assertEqual(self.data(), stock)
        self.call()
        installed = self.data()
        (self.backups / f"{module.THEME}.1:51.1-1.stock").write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "stock resource digest mismatch"):
            self.call()
        self.assertEqual(self.data(), installed)

    def test_late_swap_failure_rolls_back_the_live_layout(self):
        before = self.data()
        atomic = module.atomic_file
        def fail_theme(path, data):
            if path == self.shell / module.THEME:
                raise OSError("simulated late write failure")
            return atomic(path, data)

        with patch.object(module, "atomic_file", side_effect=fail_theme):
            with self.assertRaisesRegex(OSError, "late write failure"):
                self.call()
        self.assertEqual(self.data(), before)


if __name__ == "__main__":
    unittest.main()
