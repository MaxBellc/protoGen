"""JSON 报文解析器。

读取 JSON 文件，分离数据字段和元字段（__ 开头结尾的）。
"""

import json
import os


def parse_file(filepath: str) -> dict:
    """解析单个 JSON 报文文件。

    Args:
        filepath: JSON 文件路径

    Returns:
        dict with keys: name, fields, raw
    """
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    basename = os.path.splitext(os.path.basename(filepath))[0]

    # 处理 examples 数组: 取多示例合并分析
    examples = data.get("examples", [data])
    if not isinstance(examples, list):
        examples = [data]

    return {
        "name": basename,
        "fields": _extract_fields(examples),
        "description": data.get("__description__", ""),
        "raw": data,
    }


def _extract_fields(examples: list) -> list:
    """从示例列表中提取字段信息。

    Args:
        examples: 示例 dict 列表

    Returns:
        field dict list with keys: name, examples, meta
    """
    fields = []
    seen = set()

    for ex in examples:
        for key, value in ex.items():
            if key.startswith("__") and key.endswith("__"):
                continue  # 元字段稍后关联
            if key in seen:
                continue
            seen.add(key)
            fields.append({
                "name": key,
                "examples": _collect_field_examples(key, examples),
                "meta": _collect_meta(key, examples),
            })

    return fields


def _collect_field_examples(field_name: str, examples: list) -> list:
    """收集某个字段在所有示例中的值。"""
    result = []
    for ex in examples:
        if field_name in ex:
            result.append(ex[field_name])
    return result


def _collect_meta(field_name: str, examples: list) -> dict:
    """收集某个字段的元数据（__name_type__, __name_size__ 等）。"""
    meta = {}
    for ex in examples:
        for mk in ("type", "size", "count", "default"):
            meta_key = f"__{field_name}_{mk}__"
            if meta_key in ex:
                meta[mk] = ex[meta_key]
    return meta
