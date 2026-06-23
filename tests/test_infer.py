"""infer.py 单元测试。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from protogen.infer import infer_fields, layout_struct, _round_pow2


class TestRoundPow2(unittest.TestCase):

    def test_small_values(self):
        self.assertEqual(_round_pow2(0), 1)
        self.assertEqual(_round_pow2(1), 1)
        self.assertEqual(_round_pow2(2), 2)
        self.assertEqual(_round_pow2(3), 4)
        self.assertEqual(_round_pow2(5), 8)
        self.assertEqual(_round_pow2(9), 16)
        self.assertEqual(_round_pow2(17), 32)


class TestInferFields(unittest.TestCase):

    def test_int_small_positive(self):
        fields = [{"name": "id", "examples": [42], "meta": {}}]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "int8_t")

    def test_int_medium(self):
        fields = [{"name": "id", "examples": [1000], "meta": {}}]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "int16_t")

    def test_int_large(self):
        fields = [{"name": "id", "examples": [100000], "meta": {}}]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "int32_t")

    def test_negative_int(self):
        fields = [{"name": "val", "examples": [-5, 10], "meta": {}}]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "int8_t")

    def test_float_type(self):
        fields = [{"name": "temp", "examples": [25.5], "meta": {}}]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "float")

    def test_string_type(self):
        fields = [{"name": "name", "examples": ["hello"], "meta": {}}]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "uint8_t")
        self.assertTrue(result[0]["is_array"])
        self.assertEqual(result[0]["array_count"], 8)  # len("hello")+1=6 → 8

    def test_explicit_type_override(self):
        fields = [{
            "name": "id",
            "examples": [42],
            "meta": {"type": "uint32_t"}
        }]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "uint32_t")

    def test_array_type(self):
        fields = [{
            "name": "data",
            "examples": [[1, 2, 3]],
            "meta": {}
        }]
        result = infer_fields(fields)
        self.assertTrue(result[0]["is_array"])
        self.assertEqual(result[0]["array_count"], 4)  # 3→4 pow2

    def test_explicit_count(self):
        fields = [{
            "name": "data",
            "examples": [[1, 2]],
            "meta": {"count": 10}
        }]
        result = infer_fields(fields)
        self.assertEqual(result[0]["array_count"], 10)


class TestLayoutStruct(unittest.TestCase):

    def test_ordering_large_to_small(self):
        fields = [
            {"name": "small", "c_type": "int8_t", "c_size": 1,
             "is_array": False, "array_count": 1, "examples": [1]},
            {"name": "large", "c_type": "int32_t", "c_size": 4,
             "is_array": False, "array_count": 1, "examples": [100]},
            {"name": "medium", "c_type": "int16_t", "c_size": 2,
             "is_array": False, "array_count": 1, "examples": [50]},
        ]
        layout = layout_struct(fields)
        ordered = layout["ordered_fields"]
        # large(4) → medium(2) → small(1)
        self.assertEqual(ordered[0]["name"], "large")
        self.assertEqual(ordered[1]["name"], "medium")
        self.assertEqual(ordered[2]["name"], "small")

    def test_mask_type_selection(self):
        fields = [{"name": f"f{i}", "c_type": "int8_t", "c_size": 1,
                    "is_array": False, "array_count": 1, "examples": [1]}
                   for i in range(3)]
        layout = layout_struct(fields)
        self.assertEqual(layout["mask_type"], "uint8_t")

        fields16 = [{"name": f"f{i}", "c_type": "int8_t", "c_size": 1,
                      "is_array": False, "array_count": 1, "examples": [1]}
                     for i in range(10)]
        layout16 = layout_struct(fields16)
        self.assertEqual(layout16["mask_type"], "uint16_t")

    def test_padding(self):
        fields = [
            {"name": "a", "c_type": "int8_t", "c_size": 1,
             "is_array": False, "array_count": 1, "examples": [1]},
            {"name": "b", "c_type": "int8_t", "c_size": 1,
             "is_array": False, "array_count": 1, "examples": [1]},
        ]
        # total: mask(1) + 1+1 = 3, need _res1[1] → 4
        layout = layout_struct(fields)
        self.assertEqual(len(layout["pad_fields"]), 1)
        self.assertEqual(layout["pad_fields"][0]["name"], "_res1")
        self.assertEqual(layout["pad_fields"][0]["size"], 1)


class TestNestedObject(unittest.TestCase):
    """嵌套对象测试。"""

    def test_nested_simple(self):
        """基本嵌套对象 — 类型推断和布局。"""
        fields = [{
            "name": "pos",
            "examples": [{"x": 1.5, "y": 2.5}],
            "meta": {}
        }]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "nested")
        self.assertGreater(result[0]["c_size"], 0)
        self.assertEqual(len(result[0]["sub_fields"]), 2)
        sub_names = {f["name"] for f in result[0]["sub_fields"]}
        self.assertEqual(sub_names, {"x", "y"})

    def test_nested_dedup(self):
        """多示例嵌套对象 — 子字段去重。"""
        fields = [{
            "name": "pos",
            "examples": [
                {"x": 1.0, "y": 2.0},
                {"x": 3.0, "y": 4.0},
                {"x": 5.0, "y": 6.0},
            ],
            "meta": {}
        }]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "nested")
        # 应该只有 x, y 两个子字段（去重）
        self.assertEqual(len(result[0]["sub_fields"]), 2)

    def test_nested_multi_example_cross_ref(self):
        """多示例 — 子字段值跨示例合并用于类型推断。"""
        fields = [{
            "name": "data",
            "examples": [
                {"val": 1},
                {"val": 100000},
            ],
            "meta": {}
        }]
        result = infer_fields(fields)
        sub_val = [f for f in result[0]["sub_fields"] if f["name"] == "val"][0]
        # 100000 超出 int16_t 范围 → int32_t
        self.assertEqual(sub_val["c_type"], "int32_t")

    def test_nested_sub_fields_ordered(self):
        """子结构体字段大→小排序。"""
        fields = [{
            "name": "info",
            "examples": [{"big": 100000, "small": 1, "name": "A"}],
            "meta": {}
        }]
        result = infer_fields(fields)
        sub = result[0]["sub_fields"]
        # big(int32_t,4) > small(int8_t,1), name(uint8_t[n], n>4)
        self.assertIn(sub[0]["name"], {"name", "big"})
        # small(int8_t) 应该在最后
        self.assertEqual(sub[-1]["name"], "small")

    def test_nested_sub_meta_inside(self):
        """子字段 meta 通过内嵌 __field_type__ 指定。"""
        fields = [{
            "name": "cfg",
            "examples": [{"level": 1, "__level_type__": "uint32_t"}],
            "meta": {}
        }]
        result = infer_fields(fields)
        sub_level = [f for f in result[0]["sub_fields"] if f["name"] == "level"][0]
        self.assertEqual(sub_level["c_type"], "uint32_t")

    def test_deep_nested(self):
        """两层嵌套。"""
        fields = [{
            "name": "outer",
            "examples": [{"inner": {"value": 42}}],
            "meta": {}
        }]
        result = infer_fields(fields)
        outer = result[0]
        self.assertEqual(outer["c_type"], "nested")
        inner = [f for f in outer["sub_fields"] if f["name"] == "inner"][0]
        self.assertEqual(inner["c_type"], "nested")
        self.assertEqual(len(inner["sub_fields"]), 1)
        self.assertEqual(inner["sub_fields"][0]["name"], "value")


class TestArrayOfObjects(unittest.TestCase):
    """对象数组测试。"""

    def test_array_of_objects_simple(self):
        """基本对象数组。"""
        fields = [{
            "name": "items",
            "examples": [[{"id": 1, "val": 10.5}, {"id": 2, "val": 20.5}]],
            "meta": {}
        }]
        result = infer_fields(fields)
        self.assertEqual(result[0]["c_type"], "nested")
        self.assertTrue(result[0]["is_array"])
        self.assertEqual(result[0]["array_count"], 2)  # 2→2(已是2的幂)
        self.assertEqual(len(result[0]["sub_fields"]), 2)

    def test_array_of_objects_count(self):
        """对象数组 — 显式 count。"""
        fields = [{
            "name": "points",
            "examples": [[{"x": 1.0, "y": 2.0}]],
            "meta": {"count": 8}
        }]
        result = infer_fields(fields)
        self.assertEqual(result[0]["array_count"], 8)

    def test_array_of_objects_dedup(self):
        """多示例对象数组 — 子字段去重。"""
        fields = [{
            "name": "logs",
            "examples": [
                [{"msg": "A", "code": 1}],
                [{"msg": "BB", "code": 2}],
                [{"msg": "CCC", "code": 3}],
            ],
            "meta": {}
        }]
        result = infer_fields(fields)
        self.assertEqual(len(result[0]["sub_fields"]), 2)
        names = {f["name"] for f in result[0]["sub_fields"]}
        self.assertEqual(names, {"msg", "code"})


if __name__ == "__main__":
    unittest.main()
