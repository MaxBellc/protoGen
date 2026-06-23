"""C 代码生成器。

从解析+推导后的结构体信息，生成 .h 和 .c 文件。
零外部依赖，纯 Python 字符串拼接。

支持嵌套对象和对象数组的递归生成。
"""

import os
from datetime import date


def _indent(text: str, level: int = 1) -> str:
    """对多行文本每行加缩进。"""
    prefix = " " * (4 * level)
    return "\n".join(prefix + line if line else "" for line in text.split("\n"))


# ==============================================================================
# 顶层入口
# ==============================================================================


def generate_one(msg_info: dict, layout: dict, output_dir: str):
    """生成单个消息的 .h 和 .c 文件。

    Args:
        msg_info: 解析后的消息信息
        layout: 结构体布局
        output_dir: 输出根目录
    """
    name = msg_info["name"]
    func_prefix = _to_snake_case(name)
    file_name = func_prefix
    struct_name = _to_upper_snake(name)
    guard_name = f"{struct_name}_H"

    ordered = layout["ordered_fields"]
    mask_type = layout["mask_type"]
    pad_fields = layout["pad_fields"]

    h_path, c_path = _write_files(
        file_name, func_prefix, struct_name, guard_name,
        msg_info, ordered, mask_type, pad_fields, output_dir,
    )
    return h_path, c_path


def _write_files(file_name, func_prefix, struct_name, guard_name,
                 msg_info, ordered, mask_type, pad_fields, output_dir):
    """写入 .h 和 .c 文件。"""
    today = date.today().isoformat()
    desc = msg_info.get("description", "")

    h = _gen_header(file_name, func_prefix, struct_name, guard_name,
                    desc, ordered, mask_type, pad_fields, today)

    c = _gen_source(file_name, func_prefix, struct_name,
                    desc, ordered, mask_type, today)

    inc_dir = os.path.join(output_dir, "inc")
    src_dir = os.path.join(output_dir, "src")
    os.makedirs(inc_dir, exist_ok=True)
    os.makedirs(src_dir, exist_ok=True)

    h_path = os.path.join(inc_dir, f"{file_name}.h")
    c_path = os.path.join(src_dir, f"{file_name}.c")

    with open(h_path, "w", encoding="utf-8") as f:
        f.write(h)
    with open(c_path, "w", encoding="utf-8") as f:
        f.write(c)

    _format_file(h_path)
    _format_file(c_path)

    return h_path, c_path


# ==============================================================================
# 头文件生成
# ==============================================================================


def _gen_header(file_name, func_prefix, struct_name, guard_name,
                desc, ordered, mask_type, pad_fields, today):
    """生成 .h 文件内容。"""
    lines = []
    a = lines.append

    # ---- 文件头 ----
    a("/**")
    a(f" * @file    {file_name}.h")
    a(f" * @brief   {desc or struct_name} JSON 序列化/反序列化")
    a(" *")
    a(" * @details 由 protoGen 自动生成，请勿手动修改。")
    a(f" *          消息名: {struct_name}")
    a(" *")
    a(" * @author  protoGen")
    a(" * @version 1.0.0")
    a(f" * @date    {today}")
    a(" *")
    a(" * @copyright MIT License")
    a(" */")
    a("")
    a(f"#ifndef {guard_name}")
    a(f"#define {guard_name}")
    a("")
    a("#include <stdint.h>")
    a("#include <stddef.h>")
    a("")
    a('#include "cJSON.h"')
    a("")
    a("#ifdef __cplusplus")
    a('extern "C"')
    a("{")
    a("#endif")
    a("")

    # ---- 递归生成子结构体定义（叶子优先）----
    _gen_nested_types_header(a, struct_name, func_prefix, ordered)

    # ---- 主结构体字段枚举 ----
    a("/*===========================================================================")
    a(f" * 字段枚举 — {struct_name}")
    a(" *===========================================================================*/")
    a("")
    _gen_enum_and_mask(a, struct_name, ordered)

    # ---- 主结构体定义 ----
    a("/*===========================================================================")
    a(f" * 结构体 — {struct_name}")
    a(" *===========================================================================*/")
    a("")
    if desc:
        a("/**")
        a(f" * @brief {desc}")
        a(" */")
    _gen_struct_typedef(a, struct_name, ordered, mask_type, pad_fields)
    a("")

    # ---- JSON 序列化 / 反序列化 API ----
    a("/*===========================================================================")
    a(" * JSON 序列化 / 反序列化 (依赖 cJSON)")
    a(" *===========================================================================*/")
    a("")
    _doxygen_func(a, f"将 {struct_name} 序列化为 JSON 字符串", [
        ("[in]", "msg", "消息指针"),
        ("[out]", "json_str", "输出: JSON 字符串 (调用者需 cJSON_free 释放)"),
    ], "成功返回 0，失败返回 -1")
    a(f"int32_t {func_prefix}_serialize(const {struct_name} *msg,")
    a(f"                                char **json_str);")
    a("")
    _doxygen_func(a, f"从 JSON 字符串反序列化为 {struct_name}", [
        ("[out]", "msg", "消息指针"),
        ("[in]", "json_str", "JSON 字符串"),
    ], "成功返回 0，失败返回 -1")
    a(f"int32_t {func_prefix}_deserialize({struct_name} *msg,")
    a(f"                                const char *json_str);")
    a("")

    # ---- has_ 函数（所有字段，含 nested） ----
    a("/*===========================================================================")
    a(" * 掩码检查函数")
    a(" *===========================================================================*/")
    for f in ordered:
        a("")
        _doxygen_func(a, f"检查 {f['name']} 是否存在于报文中", [
            ("[in]", "msg", "消息指针"),
        ], "1 = 存在，0 = 不存在")
        a(f"int32_t {func_prefix}_has_{f['name']}(const {struct_name} *msg);")

    a("")
    a("#ifdef __cplusplus")
    a("}")
    a("#endif")
    a("")
    a(f"#endif /* {guard_name} */")
    return "\n".join(lines)


def _gen_nested_types_header(a, struct_name, func_prefix, fields):
    """递归生成所有嵌套子结构体定义（叶子优先）。"""
    for f in fields:
        if f.get("c_type") != "nested":
            continue
        fname = f["name"]
        sub_struct = f"{struct_name}_{fname.upper()}"
        sub_prefix = f"{func_prefix}_{fname}"
        sub_fields = f["sub_fields"]
        sub_mask = f.get("sub_mask_type", "uint8_t")
        sub_pad = f.get("sub_pad_fields", [])

        # 先递归生成更深层的子结构体
        _gen_nested_types_header(a, sub_struct, sub_prefix, sub_fields)

        # 生成当前子结构体
        label = f"{fname} 子结构体"
        if f.get("is_array"):
            label = f"{fname} 数组元素结构体"

        a("/*---------------------------------------------------------------------------")
        a(f" * {label}")
        a(" *---------------------------------------------------------------------------*/")
        a("")
        _gen_enum_and_mask(a, sub_struct, sub_fields)
        _gen_struct_typedef(a, sub_struct, sub_fields, sub_mask, sub_pad)
        a("")


# ==============================================================================
# 源文件生成
# ==============================================================================


def _gen_source(file_name, func_prefix, struct_name,
                desc, ordered, mask_type, today):
    """生成 .c 文件内容。"""
    lines = []
    a = lines.append

    # ---- 文件头 ----
    a("/**")
    a(f" * @file    {file_name}.c")
    a(f" * @brief   {struct_name} JSON 序列化/反序列化实现")
    a(" *")
    a(" * @details 由 protoGen 自动生成，请勿手动修改。")
    a(" *")
    a(" * @author  protoGen")
    a(" * @version 1.0.0")
    a(f" * @date    {today}")
    a(" *")
    a(" * @copyright MIT License")
    a(" */")
    a("")
    a(f'#include "{file_name}.h"')
    a("#include <string.h>")
    a("#include <stdlib.h>")
    a("")

    # ---- 递归生成子结构体的 JSON 辅助函数 ----
    has_nested = any(f.get("c_type") == "nested" for f in ordered)
    if has_nested:
        a("/*===========================================================================")
        a(" * 内部: 子结构体 JSON 构建/解析")
        a(" *===========================================================================*/")
        _gen_json_nested_types_source(a, struct_name, func_prefix, ordered)

    # ---- _add_to_json (static) ----
    a("")
    a("/*===========================================================================")
    a(" * 内部: JSON 构建")
    a(" *===========================================================================*/")
    a("")
    _doxygen_func(a, f"将 {struct_name} 字段添加到 cJSON 对象", [], "")
    a(f"static void {func_prefix}_add_to_json(")
    a(f"    const {struct_name} *msg, cJSON *obj)")
    a("{")
    if _json_needs_sub(ordered):
        a("    cJSON *__sub = NULL;")
    if _json_needs_arr(ordered):
        a("    cJSON *__arr = NULL;")
    has_decl2 = _json_needs_sub(ordered) or _json_needs_arr(ordered)
    if has_decl2:
        a("")
    for f in ordered:
        _gen_json_add_field(a, f, struct_name, func_prefix, "obj", "")
    a("}")

    # ---- _parse_from_json (static) ----
    a("")
    a("/*===========================================================================")
    a(" * 内部: JSON 解析")
    a(" *===========================================================================*/")
    a("")
    _doxygen_func(a, f"从 cJSON 对象中解析 {struct_name} 字段", [], "")
    a(f"static void {func_prefix}_parse_from_json(")
    a(f"    {struct_name} *msg, const cJSON *obj)")
    a("{")
    a("    cJSON  *__item = NULL;")
    if _json_needs_iter(ordered):
        a("    cJSON  *__elem = NULL;")
        a("    int32_t  __i = 0;")
    a("")
    for f in ordered:
        _gen_json_parse_field(a, f, struct_name, func_prefix, "obj", "")
    a("}")

    # ---- serialize (public) ----
    a("")
    a("/*===========================================================================")
    a(" * 公共 API: JSON 序列化")
    a(" *===========================================================================*/")
    a("")
    _doxygen_func(a, f"将 {struct_name} 序列化为 JSON 字符串", [], "")
    a(f"int32_t {func_prefix}_serialize(const {struct_name} *msg,")
    a(f"                                char **json_str)")
    a("{")
    a("    cJSON *root = NULL;")
    a("    char  *out = NULL;")
    a("")
    a("    if ((NULL == msg) || (NULL == json_str))")
    a("    {")
    a("        return -1;")
    a("    }")
    a("")
    a("    root = cJSON_CreateObject();")
    a("    if (NULL == root)")
    a("    {")
    a("        return -1;")
    a("    }")
    a("")
    a(f"    {func_prefix}_add_to_json(msg, root);")
    a("")
    a("    out = cJSON_PrintUnformatted(root);")
    a("    cJSON_Delete(root);")
    a("")
    a("    if (NULL == out)")
    a("    {")
    a("        return -1;")
    a("    }")
    a("")
    a("    *json_str = out;")
    a("    return 0;")
    a("}")

    # ---- deserialize (public) ----
    a("")
    a("/*===========================================================================")
    a(" * 公共 API: JSON 反序列化")
    a(" *===========================================================================*/")
    a("")
    _doxygen_func(a, f"从 JSON 字符串反序列化为 {struct_name}", [], "")
    a(f"int32_t {func_prefix}_deserialize({struct_name} *msg,")
    a(f"                                const char *json_str)")
    a("{")
    a("    cJSON *root = NULL;")
    a("")
    a("    if ((NULL == msg) || (NULL == json_str))")
    a("    {")
    a("        return -1;")
    a("    }")
    a("")
    a("    root = cJSON_Parse(json_str);")
    a("    if (NULL == root)")
    a("    {")
    a("        return -1;")
    a("    }")
    a("")
    a(f"    {func_prefix}_parse_from_json(msg, root);")
    a("")
    a("    cJSON_Delete(root);")
    a("    return 0;")
    a("}")

    # ---- has_ 函数 ----
    a("")
    a("/*===========================================================================")
    a(" * 公共 API: 掩码检查")
    a(" *===========================================================================*/")

    for f in ordered:
        fname = f["name"]
        field_enum = f"{struct_name}_FIELD_{fname.upper()}"
        a("")
        _doxygen_func(a, f"检查 {fname} 是否存在于报文中", [], "")
        a(f"int32_t {func_prefix}_has_{fname}(const {struct_name} *msg)")
        a("{")
        a("    if (NULL == msg)")
        a("    {")
        a("        return 0;")
        a("    }")
        a("")
        a(f"    return (msg->__mask__ & {struct_name}_MASK({field_enum}))")
        a(f"               ? 1")
        a(f"               : 0;")
        a("}")

    return "\n".join(lines)


# ==============================================================================
# 代码生成辅助函数
# ==============================================================================


def _gen_enum_and_mask(a, struct_name, fields):
    """生成字段枚举和 MASK 宏。

    包含 nested 字段 —— 父结构体的 mask 需要 nested 字段的位。
    """
    a("/** @brief 字段索引 */")
    a("enum")
    a("{")
    for i, f in enumerate(fields):
        comma = "," if i < len(fields) - 1 else ""
        a(f"    {struct_name}_FIELD_{f['name'].upper()} = {i}{comma}")
    a("};")
    a("")
    a("/** @brief 将字段索引转为 mask 位 */")
    a(f"#define {struct_name}_MASK(field)  (1u << (field))")


def _gen_struct_typedef(a, struct_name, fields, mask_type, pad_fields):
    """生成 typedef struct 定义。

    支持嵌套字段（含嵌套数组）的类型引用。
    """
    a(f"typedef struct _{struct_name}_")
    a("{")
    for f in fields:
        fname = f["name"]
        if f.get("c_type") == "nested":
            if f.get("is_array"):
                sub_type = f"{struct_name}_{fname.upper()}"
                a(f"    {sub_type}    {fname}[{f['array_count']}];  /**< {fname} 数组 */")
            else:
                sub_type = f"{struct_name}_{fname.upper()}"
                a(f"    {sub_type}    {fname};  /**< {fname} 子结构体 */")
        elif f.get("is_array"):
            a(f"    {f['c_type']}    {fname}[{f['array_count']}];  /**< {fname} */")
        else:
            a(f"    {f['c_type']}    {fname};  /**< {fname} */")
    a(f"    {mask_type}               __mask__;    /**< 字段掩码 */")
    for pad in pad_fields:
        a(f"    uint8_t                {pad['name']}[{pad['size']}];  /**< 4字节对齐保留 */")
    a(f"}} {struct_name};")


def _doxygen_func(a, brief, params, ret):
    """输出 Doxygen 函数注释。"""
    a("/**")
    a(f" * @brief {brief}")
    if params:
        a(" *")
        for direction, name, desc in params:
            a(f" * @param{direction} {name}  {desc}")
    if ret:
        a(" *")
        a(f" * @return {ret}")
    a(" */")


# ==============================================================================
# JSON 模式 (cJSON) 辅助函数
# ==============================================================================


def _json_needs_sub(fields):
    """检查是否有嵌套字段（需要 __sub 变量）。"""
    for f in fields:
        if f.get("c_type") == "nested":
            return True
    return False


def _json_needs_arr(fields):
    """检查是否有数组字段（需要 __arr 变量——基本类型数组或嵌套数组）。"""
    for f in fields:
        if f.get("is_array") and f.get("c_type") != "uint8_t":
            return True
        if f.get("c_type") == "nested" and f.get("is_array"):
            return True
    return False


def _json_needs_iter(fields):
    """检查 parse 中是否需要 __elem / __i。"""
    for f in fields:
        if f.get("c_type") == "nested" and f.get("is_array"):
            return True
        if f.get("is_array") and f.get("c_type") != "uint8_t":
            return True
    return False


def _gen_json_nested_types_source(a, struct_name, func_prefix, fields):
    """递归生成嵌套子结构体的 JSON _add_to_json / _parse_from_json。"""
    for f in fields:
        if f.get("c_type") != "nested":
            continue
        fname = f["name"]
        sub_struct = f"{struct_name}_{fname.upper()}"
        sub_prefix = f"{func_prefix}_{fname}"
        sub_fields = f["sub_fields"]

        # 先递归
        _gen_json_nested_types_source(a, sub_struct, sub_prefix, sub_fields)

        # ---- _add_to_json ----
        a("")
        _doxygen_func(a, f"将 {sub_struct} 字段添加到 cJSON 对象", [], "")
        a(f"static void {sub_prefix}_add_to_json(")
        a(f"    const {sub_struct} *msg, cJSON *obj)")
        a("{")
        if _json_needs_sub(sub_fields):
            a("    cJSON *__sub = NULL;")
        if _json_needs_arr(sub_fields):
            a("    cJSON *__arr = NULL;")
        has_decl = _json_needs_sub(sub_fields) or _json_needs_arr(sub_fields)
        if has_decl:
            a("")
        for sf in sub_fields:
            _gen_json_add_field(a, sf, sub_struct, sub_prefix, "obj", "")
        a("}")

        # ---- _parse_from_json ----
        a("")
        _doxygen_func(a, f"从 cJSON 对象中解析 {sub_struct} 字段", [], "")
        a(f"static void {sub_prefix}_parse_from_json(")
        a(f"    {sub_struct} *msg, const cJSON *obj)")
        a("{")
        a("    cJSON  *__item = NULL;")
        if _json_needs_iter(sub_fields):
            a("    cJSON  *__elem = NULL;")
            a("    int32_t  __i = 0;")
        a("")
        for sf in sub_fields:
            _gen_json_parse_field(a, sf, sub_struct, sub_prefix, "obj", "")
        a("}")


def _gen_json_add_field(a, f, struct_name, prefix, obj_var, indent):
    """Generate: if mask & bit → cJSON_AddXxxToObject(obj, name, value)."""
    fname = f["name"]
    json_name = fname
    c_type = f.get("c_type", "int32_t")
    is_array = f.get("is_array", False)
    array_count = f.get("array_count", 1)
    field_ref = f"msg->{fname}"
    field_enum = f"{struct_name}_FIELD_{fname.upper()}"
    mask_bit = f"{struct_name}_MASK({field_enum})"

    a(f"{indent}    if (msg->__mask__ & {mask_bit})")
    a(f"{indent}    {{")

    if c_type == "nested":
        sub_prefix = f"{prefix}_{fname}"
        if is_array:
            a(f"{indent}        __arr = cJSON_AddArrayToObject({obj_var}, "
              f"\"{json_name}\");")
            a(f"{indent}        for (int32_t __i = 0; __i < {array_count}; __i++)")
            a(f"{indent}        {{")
            a(f"{indent}            __sub = cJSON_CreateObject();")
            a(f"{indent}            {sub_prefix}_add_to_json(")
            a(f"{indent}                &{field_ref}[__i], __sub);")
            a(f"{indent}            cJSON_AddItemToArray(__arr, __sub);")
            a(f"{indent}        }}")
        else:
            a(f"{indent}        __sub = cJSON_AddObjectToObject({obj_var}, "
              f"\"{json_name}\");")
            a(f"{indent}        {sub_prefix}_add_to_json(&{field_ref}, __sub);")
    elif is_array:
        if c_type == "uint8_t":
            a(f"{indent}        cJSON_AddStringToObject({obj_var}, "
              f"\"{json_name}\", (const char *){field_ref});")
        else:
            a(f"{indent}        __arr = cJSON_AddArrayToObject({obj_var}, "
              f"\"{json_name}\");")
            a(f"{indent}        for (int32_t __i = 0; __i < {array_count}; __i++)")
            a(f"{indent}        {{")
            a(f"{indent}            cJSON_AddItemToArray(__arr, "
              f"cJSON_CreateNumber({field_ref}[__i]));")
            a(f"{indent}        }}")
    elif c_type in ("float", "double"):
        a(f"{indent}        cJSON_AddNumberToObject({obj_var}, "
          f"\"{json_name}\", {field_ref});")
    elif c_type == "uint8_t":
        a(f"{indent}        cJSON_AddStringToObject({obj_var}, "
          f"\"{json_name}\", (const char *){field_ref});")
    else:
        a(f"{indent}        cJSON_AddNumberToObject({obj_var}, "
          f"\"{json_name}\", {field_ref});")

    a(f"{indent}    }}")


def _gen_json_parse_field(a, f, struct_name, prefix, obj_var, indent):
    """Generate: item = cJSON_GetObjectItem; if valid → read value, set mask.  """
    fname = f["name"]
    json_name = fname
    c_type = f.get("c_type", "int32_t")
    is_array = f.get("is_array", False)
    array_count = f.get("array_count", 1)
    field_ref = f"msg->{fname}"
    field_enum = f"{struct_name}_FIELD_{fname.upper()}"
    mask_bit = f"{struct_name}_MASK({field_enum})"

    if c_type == "nested":
        sub_prefix = f"{prefix}_{fname}"
        if is_array:
            a(f"{indent}    __item = cJSON_GetObjectItem({obj_var}, \"{json_name}\");")
            a(f"{indent}    if ((NULL != __item) && cJSON_IsArray(__item))")
            a(f"{indent}    {{")
            a(f"{indent}        __i = 0;")
            a(f"{indent}        cJSON_ArrayForEach(__elem, __item)")
            a(f"{indent}        {{")
            a(f"{indent}            if (__i >= {array_count})")
            a(f"{indent}            {{")
            a(f"{indent}                break;")
            a(f"{indent}            }}")
            a(f"{indent}            if (cJSON_IsObject(__elem))")
            a(f"{indent}            {{")
            a(f"{indent}                {sub_prefix}_parse_from_json(")
            a(f"{indent}                    &{field_ref}[__i], __elem);")
            a(f"{indent}            }}")
            a(f"{indent}            __i++;")
            a(f"{indent}        }}")
            a(f"{indent}        msg->__mask__ |= {mask_bit};")
            a(f"{indent}    }}")
        else:
            a(f"{indent}    __item = cJSON_GetObjectItem({obj_var}, \"{json_name}\");")
            a(f"{indent}    if ((NULL != __item) && cJSON_IsObject(__item))")
            a(f"{indent}    {{")
            a(f"{indent}        {sub_prefix}_parse_from_json(&{field_ref}, __item);")
            a(f"{indent}        msg->__mask__ |= {mask_bit};")
            a(f"{indent}    }}")
        return

    if is_array:
        # uint8_t[] → JSON 字符串
        if c_type == "uint8_t":
            a(f"{indent}    __item = cJSON_GetObjectItem({obj_var}, \"{json_name}\");")
            a(f"{indent}    if ((NULL != __item) && cJSON_IsString(__item))")
            a(f"{indent}    {{")
            a(f"{indent}        strncpy((char *){field_ref},")
            a(f"{indent}                __item->valuestring, sizeof({field_ref}) - 1);")
            a(f"{indent}        {field_ref}[sizeof({field_ref}) - 1] = '\\0';")
            a(f"{indent}        msg->__mask__ |= {mask_bit};")
            a(f"{indent}    }}")
        else:
            # 数值数组
            a(f"{indent}    __item = cJSON_GetObjectItem({obj_var}, \"{json_name}\");")
            a(f"{indent}    if ((NULL != __item) && cJSON_IsArray(__item))")
            a(f"{indent}    {{")
            a(f"{indent}        __i = 0;")
            a(f"{indent}        cJSON_ArrayForEach(__elem, __item)")
            a(f"{indent}        {{")
            a(f"{indent}            if (__i >= {array_count})")
            a(f"{indent}            {{")
            a(f"{indent}                break;")
            a(f"{indent}            }}")
            a(f"{indent}            if ((NULL != __elem) && cJSON_IsNumber(__elem))")
            a(f"{indent}            {{")
            a(f"{indent}                {field_ref}[__i] = ({c_type})__elem->valueint;")
            a(f"{indent}            }}")
            a(f"{indent}            __i++;")
            a(f"{indent}        }}")
            a(f"{indent}        msg->__mask__ |= {mask_bit};")
            a(f"{indent}    }}")
        return

    # 标量
    a(f"{indent}    __item = cJSON_GetObjectItem({obj_var}, \"{json_name}\");")
    if c_type == "uint8_t":
        a(f"{indent}    if ((NULL != __item) && cJSON_IsString(__item))")
        a(f"{indent}    {{")
        a(f"{indent}        strncpy((char *){field_ref},")
        a(f"{indent}                __item->valuestring, sizeof({field_ref}) - 1);")
        a(f"{indent}        {field_ref}[sizeof({field_ref}) - 1] = '\\0';")
        a(f"{indent}        msg->__mask__ |= {mask_bit};")
        a(f"{indent}    }}")
    elif c_type in ("float", "double"):
        a(f"{indent}    if ((NULL != __item) && cJSON_IsNumber(__item))")
        a(f"{indent}    {{")
        a(f"{indent}        {field_ref} = ({c_type})__item->valuedouble;")
        a(f"{indent}        msg->__mask__ |= {mask_bit};")
        a(f"{indent}    }}")
    else:
        # 整数
        a(f"{indent}    if ((NULL != __item) && cJSON_IsNumber(__item))")
        a(f"{indent}    {{")
        a(f"{indent}        {field_ref} = ({c_type})__item->valueint;")
        a(f"{indent}        msg->__mask__ |= {mask_bit};")
        a(f"{indent}    }}")


# ==============================================================================
# 命名工具
# ==============================================================================


def _to_snake_case(name: str) -> str:
    """PascalCase → snake_case。"""
    result = []
    for i, ch in enumerate(name):
        if ch.isupper():
            if i > 0:
                result.append("_")
            result.append(ch.lower())
        else:
            result.append(ch)
    return "".join(result)


def _to_upper_snake(name: str) -> str:
    """PascalCase → UPPER_SNAKE_CASE。"""
    return _to_snake_case(name).upper()


def _format_file(filepath: str):
    """对生成的文件运行 clang-format。"""
    import subprocess
    try:
        subprocess.run(
            ["clang-format", "-i", filepath],
            check=True, capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass  # clang-format 未安装时静默跳过
