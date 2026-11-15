"""Regression tests for optional HeyLight RSSI diagnostics.

These tests inspect the sensor source because Home Assistant is not installed in CI.
"""

import ast
import unittest
from pathlib import Path


class TestRSSIDefaults(unittest.TestCase):
    def test_sensor_disabled_by_default(self) -> None:
        path = Path(__file__).resolve().parents[1] / "custom_components" / "heylight" / "sensor.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        cls = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "HeylightRSSISensor"
        )
        settings = {
            target.id: statement.value
            for statement in cls.body
            if isinstance(statement, ast.Assign)
            for target in statement.targets
            if isinstance(target, ast.Name)
        }
        self.assertIn("_attr_entity_registry_enabled_default", settings)
        self.assertIs(
            ast.literal_eval(settings["_attr_entity_registry_enabled_default"]),
            False,
        )


if __name__ == "__main__":
    unittest.main()
