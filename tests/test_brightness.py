"""Regression tests for the shared linear brightness curve."""

import importlib.util
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "heylight_brightness",
    Path(__file__).resolve().parents[1] / "custom_components/heylight/brightness.py",
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TestBrightness(unittest.TestCase):
    def test_endpoints(self):
        self.assertAlmostEqual(module.physical_brightness_factor(1), 0.30)
        self.assertAlmostEqual(module.physical_brightness_factor(255), 1.0)

    def test_midpoint(self):
        self.assertAlmostEqual(module.physical_brightness_factor(128), 0.65)

    def test_clamp(self):
        self.assertAlmostEqual(module.physical_brightness_factor(-10), 0.30)
        self.assertAlmostEqual(module.physical_brightness_factor(999), 1.0)

    def test_monotonic(self):
        values = [module.physical_brightness_factor(i) for i in range(1, 256)]
        self.assertTrue(all(x < y for x, y in zip(values, values[1:])))


if __name__ == "__main__":
    unittest.main()
