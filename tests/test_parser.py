"""parser.py 单元测试。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from protogen.parser import parse_file


class TestParser(unittest.TestCase):

    def _write_json(self, data):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump(data, tmp)
        tmp.close()
        return tmp.name

    def test_basic_message(self):
        data = {"device_id": 1234, "temp": 25.5, "unit": "Celsius"}
        path = self._write_json(data)
        result = parse_file(path)
        os.unlink(path)

        self.assertIn("name", result)
        self.assertEqual(len(result["fields"]), 3)
        names = {f["name"] for f in result["fields"]}
        self.assertEqual(names, {"device_id", "temp", "unit"})

    def test_meta_fields_excluded(self):
        data = {"value": 100, "__value_type__": "uint8", "__value_size__": 4}
        path = self._write_json(data)
        result = parse_file(path)
        os.unlink(path)

        self.assertEqual(len(result["fields"]), 1)
        field = result["fields"][0]
        self.assertEqual(field["name"], "value")
        self.assertEqual(field["meta"]["type"], "uint8")
        self.assertEqual(field["meta"]["size"], 4)

    def test_multi_examples(self):
        data = {
            "examples": [
                {"x": 1, "y": 2},
                {"x": 100, "y": 200},
            ]
        }
        path = self._write_json(data)
        result = parse_file(path)
        os.unlink(path)

        self.assertEqual(len(result["fields"]), 2)
        field_x = [f for f in result["fields"] if f["name"] == "x"][0]
        self.assertEqual(set(field_x["examples"]), {1, 100})

    def test_duplicate_fields_deduped(self):
        data = {
            "examples": [
                {"a": 1},
                {"a": 2},
            ]
        }
        path = self._write_json(data)
        result = parse_file(path)
        os.unlink(path)

        self.assertEqual(len(result["fields"]), 1)


if __name__ == "__main__":
    unittest.main()
