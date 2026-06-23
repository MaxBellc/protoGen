"""类型推导引擎。

从 JSON 示例值推断 C 类型，计算结构体布局和对齐。
"""

import math
import re

# 类型到 sizeof 的映射
TYPE_SIZE = {
    "int8_t": 1, "int16_t": 2, "int32_t": 4, "int64_t": 8,
    "uint8_t": 1, "uint16_t": 2, "uint32_t": 4, "uint64_t": 8,
    "float": 4, "double": 8,
}


def infer_fields(fields: list) -> list:
    """对所有字段执行类型推断。

    Args:
        fields: parser 输出的字段列表

    Returns:
        补充了 c_type, c_size, is_array, array_count 的字段列表
    """
    result = []
    for f in fields:
        resolved = _infer_single(f)
        result.append(resolved)
    return result


def _infer_single(field: dict) -> dict:
    """推断单个字段的 C 类型。"""
    meta = field.get("meta", {})
    examples = field.get("examples", [])
    name = field["name"]

    # 1. 无示例值 → 兜底
    if not examples:
        resolved = {"name": name, "c_type": "int32_t", "c_size": 4,
                    "is_array": False, "array_count": 1, "examples": []}
        _apply_size_and_count(resolved, meta)
        if "type" in meta and meta["type"] in TYPE_SIZE:
            resolved["c_type"] = meta["type"]
            resolved["c_size"] = TYPE_SIZE[meta["type"]]
        return resolved

    first = examples[0]

    # 2. 数组 — __type__ 指定元素类型
    if isinstance(first, list):
        return _infer_array(field, meta)

    # 3. 嵌套对象
    if isinstance(first, dict):
        return _infer_nested(field, meta)

    # 4. 元字段显式类型覆盖（标量字段）
    if "type" in meta:
        c_type = meta["type"]
        if c_type in TYPE_SIZE:
            resolved = {"name": name, "c_type": c_type,
                        "c_size": TYPE_SIZE[c_type], "is_array": False,
                        "array_count": 1, "examples": examples}
            _apply_size_and_count(resolved, meta)
            return resolved

    # 5. 字符串
    if isinstance(first, str):
        return _infer_string(field, meta)

    # 6. 整数/浮点
    if isinstance(first, bool):
        return _infer_int(field, meta, examples)

    if isinstance(first, int):
        return _infer_int(field, meta, examples)

    if isinstance(first, float):
        return _infer_float(field, meta, examples)

    # 兜底
    resolved = {"name": name, "c_type": "int32_t", "c_size": 4,
                "is_array": False, "array_count": 1, "examples": examples}
    _apply_size_and_count(resolved, meta)
    return resolved


def _infer_int(field, meta, examples):
    name = field["name"]
    vals = [abs(v) for v in examples if isinstance(v, (int, float))]
    max_val = max(vals) if vals else 0
    has_negative = any(v < 0 for v in examples if isinstance(v, (int, float)))

    if max_val <= 127:
        c_type = "int8_t"
    elif max_val <= 32767:
        c_type = "int16_t"
    elif max_val <= 2147483647:
        c_type = "int32_t"
    else:
        c_type = "int64_t"

    # bool 视为 int8_t
    if all(isinstance(v, bool) for v in examples):
        c_type = "int8_t"

    resolved = {"name": name, "c_type": c_type, "c_size": TYPE_SIZE[c_type],
                "is_array": False, "array_count": 1, "examples": examples}
    _apply_size_and_count(resolved, meta)
    return resolved


def _infer_float(field, meta, examples):
    name = field["name"]
    use_double = False
    for v in examples:
        if isinstance(v, float):
            s = f"{v:.10g}"
            if len(s.replace(".", "").replace("-", "")) > 7:
                use_double = True
                break
    c_type = "double" if use_double else "float"
    resolved = {"name": name, "c_type": c_type, "c_size": TYPE_SIZE[c_type],
                "is_array": False, "array_count": 1, "examples": examples}
    _apply_size_and_count(resolved, meta)
    return resolved


def _infer_string(field, meta):
    name = field["name"]
    max_len = 1
    for v in field["examples"]:
        if isinstance(v, str):
            max_len = max(max_len, len(v) + 1)  # +1 for null terminator

    size = _round_pow2(max_len)
    if "size" in meta:
        size = meta["size"]

    resolved = {"name": name, "c_type": "uint8_t", "c_size": 1,
                "is_array": True, "array_count": size,
                "examples": field["examples"]}
    return resolved


def _infer_array(field, meta):
    """推断数组类型。

    支持基本类型数组和对象数组。对象数组会生成嵌套子结构体。
    """
    name = field["name"]

    # 收集所有元素
    all_elements = []
    for v in field["examples"]:
        if isinstance(v, list):
            all_elements.extend(v)

    max_count = max(len(v) for v in field["examples"] if isinstance(v, list))
    count = _round_pow2(max_count)
    if "count" in meta:
        count = meta["count"]

    if not all_elements:
        resolved = {"name": name, "c_type": "int32_t", "c_size": 4,
                    "is_array": True, "array_count": count,
                    "examples": field["examples"]}
        return resolved

    first_elem = all_elements[0]

    # 对象数组 → 生成嵌套子结构体
    if isinstance(first_elem, dict):
        return _infer_nested_array(field, meta, all_elements, count)

    # 基本类型数组
    elem_type = "int32_t"
    if isinstance(first_elem, float):
        elem_type = "float"
    elif isinstance(first_elem, str):
        elem_type = "uint8_t"

    if "type" in meta:
        elem_type = meta["type"]

    resolved = {"name": name, "c_type": elem_type,
                "c_size": TYPE_SIZE.get(elem_type, 4),
                "is_array": True, "array_count": count,
                "examples": field["examples"]}
    return resolved


def _infer_nested_array(field, meta, all_elements, count):
    """推断对象数组 — 收集所有元素对象的字段，生成子结构体。"""
    name = field["name"]
    sub_fields = _collect_nested_sub_fields(all_elements)
    sub_fields = infer_fields(sub_fields)
    sub_layout = layout_struct(sub_fields)

    resolved = {
        "name": name,
        "c_type": "nested",
        "c_size": sub_layout["total_size"],
        "is_array": True,
        "array_count": count,
        "sub_fields": sub_layout["ordered_fields"],
        "sub_mask_type": sub_layout["mask_type"],
        "sub_mask_size": sub_layout["mask_size"],
        "sub_pad_fields": sub_layout["pad_fields"],
        "examples": field["examples"],
    }
    return resolved


def _collect_nested_sub_fields(dict_examples: list) -> list:
    """从多个 dict 示例中收集去重的子字段列表。

    同时收集内嵌的 __field_type__ / __field_size__ 等元字段。

    Args:
        dict_examples: dict 列表（嵌套对象的值或对象数组的每个元素）

    Returns:
        去重合并后的字段列表（未经类型推断）
    """
    # sub_field_map: name -> {"examples": [...], "meta": {...}}
    sub_field_map = {}

    for d in dict_examples:
        if not isinstance(d, dict):
            continue

        # 第一遍: 收集数据字段值
        for k, val in d.items():
            if k.startswith("__") and k.endswith("__"):
                continue
            if k not in sub_field_map:
                sub_field_map[k] = {"examples": [], "meta": {}}
            sub_field_map[k]["examples"].append(val)

        # 第二遍: 收集子字段的元字段
        for meta_key, meta_val in d.items():
            if not (meta_key.startswith("__") and meta_key.endswith("__")):
                continue
            inner = meta_key[2:-2]  # 去掉首尾 __
            for mk in ("type", "size", "count", "default"):
                suffix = f"_{mk}"
                if inner.endswith(suffix):
                    sub_name = inner[:-len(suffix)]
                    if sub_name in sub_field_map:
                        sub_field_map[sub_name]["meta"][mk] = meta_val
                    break

    # 构建字段列表
    result = []
    for k, v in sub_field_map.items():
        result.append({
            "name": k,
            "examples": v["examples"],
            "meta": v["meta"],
        })

    return result


def _infer_nested(field, meta):
    """推断嵌套对象类型。

    收集子字段、去重、递归推断、大→小排序。
    """
    name = field["name"]

    # 收集所有 dict 示例
    dict_examples = [v for v in field["examples"] if isinstance(v, dict)]

    # 收集去重的子字段
    all_fields = _collect_nested_sub_fields(dict_examples)

    if not all_fields:
        # 空对象 — 兜底
        resolved = {"name": name, "c_type": "int32_t", "c_size": 4,
                    "is_array": False, "array_count": 1,
                    "examples": field["examples"]}
        return resolved

    # 递归推断子字段类型
    sub_fields = infer_fields(all_fields)

    # 对子字段做大→小排序和布局计算
    sub_layout = layout_struct(sub_fields)

    resolved = {
        "name": name,
        "c_type": "nested",
        "c_size": sub_layout["total_size"],
        "is_array": False,
        "array_count": 1,
        "sub_fields": sub_layout["ordered_fields"],
        "sub_mask_type": sub_layout["mask_type"],
        "sub_mask_size": sub_layout["mask_size"],
        "sub_pad_fields": sub_layout["pad_fields"],
        "examples": field["examples"],
    }
    return resolved


def _apply_size_and_count(resolved, meta):
    """应用显式的 size/count 元字段。"""
    if "size" in meta:
        resolved["is_array"] = True
        resolved["array_count"] = meta["size"]
    if "count" in meta:
        resolved["is_array"] = True
        resolved["array_count"] = meta["count"]


def _round_pow2(n: int) -> int:
    """向上取 2 的幂。"""
    if n <= 1:
        return 1
    return 1 << (n - 1).bit_length()


def layout_struct(fields: list) -> dict:
    """计算结构体布局: 大→小排序, mask 类型, _res 填充。

    递归处理嵌套字段的子结构体。

    Args:
        fields: 已推断类型的字段列表

    Returns:
        dict with keys: ordered_fields, mask_type, mask_size,
                        pad_fields, total_size, effective_count
    """
    data_fields = []
    nested_fields = []

    for f in fields:
        if f.get("c_type") == "nested":
            nested_fields.append(f)
        else:
            data_fields.append(f)

    # 大 → 小排序: 数据字段按 c_size * array_count 降序
    for f in data_fields:
        f["total_size"] = f["c_size"] * f.get("array_count", 1)

    data_fields.sort(key=lambda f: f["total_size"], reverse=True)
    nested_fields.sort(key=lambda f: _nested_total_size(f), reverse=True)

    ordered = nested_fields + data_fields

    # mask 类型: 按全部字段数（含 nested）选择
    effective_count = len(ordered)
    if effective_count <= 8:
        mask_type = "uint8_t"
        mask_size = 1
    elif effective_count <= 16:
        mask_type = "uint16_t"
        mask_size = 2
    elif effective_count <= 32:
        mask_type = "uint32_t"
        mask_size = 4
    else:
        mask_type = "uint64_t"
        mask_size = 8

    # 计算总大小 — nested 字段贡献其 c_size（即子结构体总大小）
    total = mask_size
    for f in ordered:
        if f.get("c_type") == "nested":
            f["total_size"] = f["c_size"]  # _infer_nested 已设为子布局 total
        total += f.get("total_size", f.get("c_size", 0) * f.get("array_count", 1))

    # 计算 _res 填充
    remainder = total % 4
    pad_fields = []
    pad_idx = 1
    if remainder != 0:
        pad_size = 4 - remainder
        pad_fields.append({"name": f"_res{pad_idx}", "size": pad_size})
        total += pad_size

    return {
        "ordered_fields": ordered,
        "mask_type": mask_type,
        "mask_size": mask_size,
        "pad_fields": pad_fields,
        "total_size": total,
        "effective_count": effective_count,
    }


def _nested_total_size(field: dict) -> int:
    """递归计算嵌套子结构体的总大小（包含子 mask 和 padding）。"""
    if field.get("c_type") == "nested":
        # c_size 由 _infer_nested 设为 sub_layout["total_size"]
        return field.get("c_size", 0)
    return field.get("c_size", 0) * field.get("array_count", 1)
