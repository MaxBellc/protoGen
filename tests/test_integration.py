"""完整流程集成测试。"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from protogen.parser import parse_file
from protogen.infer import infer_fields, layout_struct
from protogen.generator import generate_one

CJSON_INC = os.environ.get("CJSON_INC", "/usr/local/include")


class TestIntegration(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _write_json(self, name, data):
        path = os.path.join(self.tmpdir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_full_pipeline(self):
        data = {
            "device_id": 1234,
            "temp": 25.5,
            "unit": "Celsius",
            "__unit_size__": 16,
        }
        path = self._write_json("TemperatureReport.json", data)

        msg = parse_file(path)
        fields = infer_fields(msg["fields"])
        layout = layout_struct(fields)

        out = os.path.join(self.tmpdir, "output")
        h_path, c_path = generate_one(msg, layout, out)

        self.assertTrue(os.path.exists(h_path))
        self.assertTrue(os.path.exists(c_path))

        # 检查 .h 内容
        with open(h_path) as f:
            header = f.read()

        self.assertIn("#ifndef TEMPERATURE_REPORT_H", header)
        self.assertIn("typedef struct _TEMPERATURE_REPORT_", header)
        self.assertIn("TEMPERATURE_REPORT_FIELD_DEVICE_ID", header)
        self.assertIn("TEMPERATURE_REPORT_MASK(field)", header)
        self.assertIn("temperature_report_serialize", header)
        self.assertIn("temperature_report_deserialize", header)
        self.assertIn("temperature_report_has_device_id", header)
        self.assertIn("temperature_report_has_temp", header)
        self.assertIn("temperature_report_has_unit", header)
        self.assertIn("__mask__", header)
        self.assertIn("_res", header)  # 对齐填充
        self.assertIn('#include "cJSON.h"', header)
        self.assertIn("char **json_str", header)

        # 检查 .c 内容
        with open(c_path) as f:
            source = f.read()

        self.assertIn('NULL == msg', source)
        self.assertIn('return -1', source)
        self.assertIn('cJSON_CreateObject', source)
        self.assertIn('cJSON_Parse', source)
        self.assertIn('cJSON_PrintUnformatted', source)

    def test_nested_compiles(self):
        """嵌套对象生成的代码能通过 gcc 编译且 clang-format 通过。"""
        import subprocess
        data = {
            "id": 1,
            "name": "dev1",
            "location": {"x": 10.5, "y": 20.3}
        }
        path = self._write_json("Device.json", data)

        msg = parse_file(path)
        fields = infer_fields(msg["fields"])
        layout = layout_struct(fields)
        out = os.path.join(self.tmpdir, "output")
        h_path, c_path = generate_one(msg, layout, out)

        # 编译
        result = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-Wdeclaration-after-statement", "-c", c_path,
             "-I", os.path.join(out, "inc"),
             "-I", CJSON_INC,
             "-o", "/dev/null"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"Compile failed: {result.stderr}")

        # 检查子结构体正确生成
        with open(h_path) as f:
            header = f.read()
        self.assertIn("DEVICE_LOCATION_MASK", header)
        self.assertIn("DEVICE_LOCATION_FIELD_X", header)
        self.assertIn("DEVICE_LOCATION_FIELD_Y", header)
        self.assertIn("DEVICE_LOCATION", header)
        self.assertIn("DEVICE_FIELD_LOCATION", header)
        self.assertIn("device_has_location", header)
        self.assertIn("device_has_id", header)
        self.assertIn("device_has_name", header)

    def test_deep_nested_compiles(self):
        """深层嵌套生成的代码能通过 gcc 编译。"""
        import subprocess
        data = {
            "id": 1,
            "outer": {"inner": {"value": 42}, "flag": True}
        }
        path = self._write_json("Deep.json", data)

        msg = parse_file(path)
        fields = infer_fields(msg["fields"])
        layout = layout_struct(fields)
        out = os.path.join(self.tmpdir, "output")
        h_path, c_path = generate_one(msg, layout, out)

        result = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-Wdeclaration-after-statement", "-c", c_path,
             "-I", os.path.join(out, "inc"),
             "-I", CJSON_INC,
             "-o", "/dev/null"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"Compile failed: {result.stderr}")

        with open(h_path) as f:
            header = f.read()
        self.assertIn("DEEP_OUTER_INNER", header)
        self.assertIn("DEEP_OUTER_INNER_FIELD_VALUE", header)
        self.assertIn("DEEP_OUTER_INNER_MASK", header)
        self.assertIn("DEEP_OUTER", header)
        self.assertIn("DEEP_OUTER_FIELD_INNER", header)

    def test_array_objects_compiles(self):
        """对象数组生成的代码能通过 gcc 编译。"""
        import subprocess
        data = {
            "id": 1,
            "readings": [
                {"temp": 25.5, "time": 1000},
                {"temp": 26.0, "time": 2000},
            ]
        }
        path = self._write_json("Sensor.json", data)

        msg = parse_file(path)
        fields = infer_fields(msg["fields"])
        layout = layout_struct(fields)
        out = os.path.join(self.tmpdir, "output")
        h_path, c_path = generate_one(msg, layout, out)

        result = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-Wdeclaration-after-statement", "-c", c_path,
             "-I", os.path.join(out, "inc"),
             "-I", CJSON_INC,
             "-o", "/dev/null"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"Compile failed: {result.stderr}")

        with open(h_path) as f:
            header = f.read()
        self.assertIn("SENSOR_READINGS", header)
        self.assertIn("SENSOR_READINGS_FIELD_TEMP", header)
        self.assertIn("SENSOR_READINGS_MASK", header)
        self.assertIn("readings[2]", header)
        self.assertIn("sensor_has_readings", header)

    def test_compiles(self):
        """验证生成的代码能通过 gcc 编译。"""
        import subprocess
        data = {"value": 42, "label": "test", "__label_size__": 8}
        path = self._write_json("SimpleMsg.json", data)

        msg = parse_file(path)
        fields = infer_fields(msg["fields"])
        layout = layout_struct(fields)
        out = os.path.join(self.tmpdir, "output")
        _, c_path = generate_one(msg, layout, out)

        result = subprocess.run(
            ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
             "-Wdeclaration-after-statement", "-c", c_path,
             "-I", os.path.join(out, "inc"),
             "-I", CJSON_INC,
             "-o", "/dev/null"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"Compile failed: {result.stderr}")

        # 验证 JSON API 存在
        with open(os.path.join(out, "inc", "simple_msg.h")) as f:
            header = f.read()
        self.assertIn("serialize", header)
        self.assertIn("deserialize", header)
        self.assertIn('#include "cJSON.h"', header)
        self.assertIn("char **json_str", header)


if __name__ == "__main__":
    unittest.main()
