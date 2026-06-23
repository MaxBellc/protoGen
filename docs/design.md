# protoGen — 协议代码生成器 设计文档

## 1. 设计目标

一个 JSON 文件 = 一个报文结构体。从示例值自动推断类型，生成 C 语言序列化/反序列化代码。

| 特性 | 说明 |
|------|------|
| 输入 | JSON 报文示例文件 |
| 输出 | `.h` + `.c`（struct + JSON serialize/deserialize） |
| 类型推导 | 从示例值自动推断，`__name__` 元字段可覆盖 |
| 命名 | 文件名即消息名（PascalCase → `UPPER_SNAKE_CASE`） |
| 编码 | JSON（cJSON），人可读、跨语言互通 |
| 生成代码 | 遵循项目编码规范 |

## 2. 报文文件格式

### 2.1 基本格式

```json
// TemperatureReport.json
{
  "device_id": 1234,
  "temp": 25.5,
  "unit": "Celsius",
  "__unit_size__": 16
}
```

| 元字段 | 作用 | 必须 |
|--------|------|------|
| `__description__` | 消息描述 | 否，写入 Doxygen |
| `__{name}_type__` | 显式指定字段类型 | 否 |
| `__{name}_size__` | 字符串/bytes 缓冲区长度 | 否，否则按示例长度取 2 的幂 |
| `__{name}_count__` | 数组元素个数 | 否，否则按示例长度取 2 的幂 |

### 2.2 类型推导规则

默认推导为**有符号**类型。无符号仅当显式指定或用于字符串缓冲区。

| 示例值 | 推断类型 | sizeof |
|--------|---------|--------|
| `0` ~ `127` / 无负数 | `int8_t` | 1 |
| `-128` ~ `127` | `int8_t` | 1 |
| `128` ~ `32767` | `int16_t` | 2 |
| `-32768` ~ `32767` | `int16_t` | 2 |
| `32768` ~ `2147483647` | `int32_t` | 4 |
| 超出以上 | `int64_t` | 8 |
| `25.5` / `-3.14` | `float` | 4 |
| 超过 7 位有效数字 | `double` | 8 |
| `"hello"` | `uint8_t[n]` | n = 向上取 2 的幂 |
| `true` / `false` | `int8_t` | 1 |

字符串/数组长度取 2 的幂：`3→4`, `5→8`, `9→16`, `17→32` ...

### 2.3 数组

```json
// SensorArray.json
{
  "values": [25.0, 26.0, 27.0],
  "__values_type__": "float"
}
```

- count 不指定 → 示例长度 3 → 向上取 2 的幂 → 4
- type 不指定 → 从首元素 `25.0` 推导为 `float`

### 2.4 多示例增强推导

```json
// TemperatureReport.json
{
  "examples": [
    {"device_id": 1,    "temp": 25.5, "unit": "C"},
    {"device_id": 1234, "temp": -5.0, "unit": "Fahrenheit"},
    {"device_id": 50000, "temp": 100.0, "unit": "Kelvin"}
  ]
}
```

多示例分析：`device_id` 范围 1~50000 → `int32_t`；`temp` 有负数 → 强制浮点；`unit` 最长 10 → `uint8_t[16]`。

## 3. 嵌套对象

JSON 中某个字段的值是另一个 JSON 对象时，生成子结构体和内部序列化函数。

```json
// DeviceReport.json
{
  "id": 1,
  "location": {
    "x": 10.5,
    "y": 20.3
  }
}
```

生成子结构体（命名规则：`{父名}_{字段名}`）：

```c
typedef struct _DEVICE_REPORT_LOCATION_
{
    float   x;        /**< x 坐标 */
    float   y;        /**< y 坐标 */
    uint8_t __mask__; /**< 字段掩码 */
} DEVICE_REPORT_LOCATION;

/* 内部 JSON 构建 —— 将子结构体字段添加到父 cJSON 对象 */
static void device_report_location_add_to_json(
    const DEVICE_REPORT_LOCATION *msg, cJSON *obj);

/* 内部 JSON 解析 —— 从 cJSON 对象解析子结构体字段 */
static void device_report_location_parse_from_json(
    DEVICE_REPORT_LOCATION *msg, const cJSON *obj);
```

父结构体引用子结构体：

```c
typedef struct _DEVICE_REPORT_
{
    DEVICE_REPORT_LOCATION   location;   /**< 位置信息 */
    int32_t                  id;         /**< 设备ID */
    uint8_t                  __mask__;   /**< 字段掩码 */
    uint8_t                  _res1[3];   /**< 对齐保留 */
} DEVICE_REPORT;
```

父序列化函数内部调用子 JSON 构建，代码可读：

```c
int32_t device_report_serialize(const DEVICE_REPORT *msg,
                                char **json_str)
{
    cJSON *root = NULL;
    char  *out = NULL;

    if ((NULL == msg) || (NULL == json_str)) { return -1; }

    root = cJSON_CreateObject();
    if (NULL == root) { return -1; }

    device_report_add_to_json(msg, root);

    out = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (NULL == out) { return -1; }

    *json_str = out;
    return 0;
}
```

嵌套深度不限，每层生成子 struct + 内部 JSON 函数。

## 4. 字段掩码

每个结构体自动生成一个 `__mask__` 字段。类型按字段数自动选择：

| 字段数 | mask 类型 | sizeof |
|--------|----------|--------|
| 1 ~ 8 | `uint8_t` | 1 |
| 9 ~ 16 | `uint16_t` | 2 |
| 17 ~ 32 | `uint32_t` | 4 |
| 33 ~ 64 | `uint64_t` | 8 |

每个 bit 对应一个**数据字段**（`__` 开头的元字段、`__mask__` 自身、`_res` 填充不计入）。bit 0 = 第 1 个数据字段。

```c
// 成员从大到小排列，尾部不足 4 字节整数倍自动补 _res
// __mask__ 类型按字段数量自动选择
typedef struct _TEMPERATURE_REPORT_
{
    uint8_t  unit[16];    /**< bit 2 — 单位字符串 */
    float    temp;        /**< bit 1 — 温度值 */
    int32_t  device_id;   /**< bit 0 — 设备ID */
    uint8_t  __mask__;    /**< 字段掩码 */
    uint8_t  _res1[3];    /**< 4 字节对齐 (16+4+4+1=25→28) */
} TEMPERATURE_REPORT;
```

### 序列化 —— 按 mask 选择性输出

每个字段自动生成一个枚举值（从 0 开始递增），配合 `_MASK()` 宏转换为位掩码：

```c
// 生成在 temperature_report.h 中
enum {
    TEMPERATURE_REPORT_FIELD_DEVICE_ID = 0,
    TEMPERATURE_REPORT_FIELD_TEMP      = 1,
    TEMPERATURE_REPORT_FIELD_UNIT      = 2,
};

#define TEMPERATURE_REPORT_MASK(field)  (1u << (field))
```

枚举值 0, 1, 2 直观好理解，`_MASK()` 宏负责转换为 bitmask。

调用者代码：

```c
TEMPERATURE_REPORT msg;

/* 序列化：只输出 device_id 和 unit */
msg.__mask__ = TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_DEVICE_ID)
             | TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_UNIT);

/* JSON 序列化 → json_str = {"device_id":42,"unit":"Celsius"} */
char *json_str = NULL;
temperature_report_serialize(&msg, &json_str);
cJSON_free(json_str);
```

生成的 serialize/deserialize 内部：

```c
/* _add_to_json: 按 mask 选择性添加字段到 cJSON 对象 */
static void temperature_report_add_to_json(
    const TEMPERATURE_REPORT *msg, cJSON *obj)
{
    if (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_DEVICE_ID)) {
        cJSON_AddNumberToObject(obj, "device_id", msg->device_id);
    }
    if (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_TEMP)) {
        cJSON_AddNumberToObject(obj, "temp", msg->temp);
    }
    if (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_UNIT)) {
        cJSON_AddStringToObject(obj, "unit", (const char *)msg->unit);
    }
}

/* _parse_from_json: 解析 JSON 并设置 mask */
static void temperature_report_parse_from_json(
    TEMPERATURE_REPORT *msg, const cJSON *obj)
{
    cJSON *__item = NULL;

    __item = cJSON_GetObjectItem(obj, "device_id");
    if ((NULL != __item) && cJSON_IsNumber(__item)) {
        msg->device_id = (int32_t)__item->valueint;
        msg->__mask__ |= TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_DEVICE_ID);
    }
    __item = cJSON_GetObjectItem(obj, "temp");
    if ((NULL != __item) && cJSON_IsNumber(__item)) {
        msg->temp = (float)__item->valuedouble;
        msg->__mask__ |= TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_TEMP);
    }
    __item = cJSON_GetObjectItem(obj, "unit");
    if ((NULL != __item) && cJSON_IsString(__item)) {
        strncpy((char *)msg->unit, __item->valuestring, sizeof(msg->unit) - 1);
        msg->unit[sizeof(msg->unit) - 1] = '\0';
        msg->__mask__ |= TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_UNIT);
    }
}
```

### 掩码检查函数

每个有效字段自动生成一个 `has_` 函数，封装 mask 位判断：

```c
// 生成在 temperature_report.h 中
int32_t temperature_report_has_device_id(const TEMPERATURE_REPORT *msg);
int32_t temperature_report_has_temp(const TEMPERATURE_REPORT *msg);
int32_t temperature_report_has_unit(const TEMPERATURE_REPORT *msg);
```

实现：

```c
int32_t temperature_report_has_temp(const TEMPERATURE_REPORT *msg)
{
    if (NULL == msg) { return 0; }
    return (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_TEMP)) ? 1 : 0;
}
```

调用者不再直接操作 mask：

```c
TEMPERATURE_REPORT msg;
temperature_report_deserialize(&msg, json_str);

if (temperature_report_has_temp(&msg)) {
    printf("temp = %.1f\n", msg.temp);
} else {
    /* 对方没传温度字段，用默认值 */
    msg.temp = 25.0f;
}
```

调用者通过检查 mask 知道哪些字段是从报文中实际解析出来的：

```c
if (temperature_report_has_temp(&msg)) {
    // temp 是从 JSON 中解析出来的
    printf("temp = %.1f\n", msg.temp);
} else {
    // temp 不在 JSON 中，msg.temp 保持旧值
}
```

## 5. 编码规范

生成的代码**必须**遵循项目编码规范，clang-format 通过后直接可用。生成器需确保：

```
✓ 文件头         @file @brief @author 完整 Doxygen
✓ 头文件保护     #ifndef TEMPERATURE_REPORT_H
✓ 结构体         typedef struct _UPPER_CASE_ { ... } UPPER_CASE;
✓ 枚举           成员 UPPER_SNAKE_CASE，值对齐
✓ 成员排序       大类型在前，小类型在后
✓ 4字节对齐      尾部不足补 _res1, _res2 ...
✓ 类型           无 int/char，全部 int32_t/uint8_t 等定宽类型
✓ Doxygen       @param[in] / @param[out] / @param[inout] / @return
✓ Yoda 条件      NULL == ptr, 0 == var
✓ 复合条件       ((NULL == a) || (NULL == b)) 加括号
✓ Allman 括号    if (...) { 换行 } 独占一行
✓ 4 空格缩进     80 列
✓ 变量声明       函数顶部声明并初始化
✓ void 函数      return;
✓ 空行           } 后 + if/while/for 前空行
✓ mask 类型      字段数 ≤8→uint8_t, ≤16→uint16_t, ≤32→uint32_t
✓ has_ 函数      每个字段一个，封装 mask 检查
✓ 空指针校验     所有指针参数入口检查 NULL
✓ 零 malloc      生成代码不分配内存，JSON 字符串由 cJSON 分配、调用者 cJSON_free
✓ const 入参     serialize 的 msg 参数、deserialize 的 json_str 参数
✓ strncpy 防溢出 字符串解析统一 strncpy + 末尾强置 \0
✓ 数组越界保护   数值数组反序列化检查 __i >= array_count
```

生成的代码**不分配内存**（零 malloc），JSON 字符串由 cJSON 内部分配，调用者负责 `cJSON_free` 释放。

生成后在代码中直接写死格式，不需要用户手动调 clang-format。但**必须通过 clang-format 检查**。

## 6. 生成的 C 代码（顶层）

### 6.1 输入

```json
// TemperatureReport.json
{
  "device_id": 1234,
  "temp": 25.5,
  "unit": "Celsius",
  "__unit_size__": 16
}
```

### 6.2 输出 — temperature_report.h

```c
#ifndef TEMPERATURE_REPORT_H
#define TEMPERATURE_REPORT_H

#include <stdint.h>
#include <stddef.h>
#include "cJSON.h"

enum {
    TEMPERATURE_REPORT_FIELD_UNIT = 0,
    TEMPERATURE_REPORT_FIELD_TEMP = 1,
    TEMPERATURE_REPORT_FIELD_DEVICE_ID = 2,
};
#define TEMPERATURE_REPORT_MASK(field)  (1u << (field))

typedef struct _TEMPERATURE_REPORT_
{
    uint8_t  unit[16];   /**< 单位字符串 */
    float    temp;       /**< 温度值 */
    int32_t  device_id;  /**< 设备ID */
    uint8_t  __mask__;   /**< 字段掩码 */
    uint8_t  _res1[3];   /**< 对齐保留 */
} TEMPERATURE_REPORT;

/* JSON 序列化：msg → JSON 字符串（调用者需 cJSON_free *json_str） */
int32_t temperature_report_serialize(const TEMPERATURE_REPORT *msg,
                                     char **json_str);

/* JSON 反序列化：JSON 字符串 → msg */
int32_t temperature_report_deserialize(TEMPERATURE_REPORT *msg,
                                       const char *json_str);

/* 掩码检查 */
int32_t temperature_report_has_device_id(const TEMPERATURE_REPORT *msg);
int32_t temperature_report_has_temp(const TEMPERATURE_REPORT *msg);
int32_t temperature_report_has_unit(const TEMPERATURE_REPORT *msg);

#endif
```

### 6.3 输出 — temperature_report.c

```c
#include "temperature_report.h"
#include <string.h>
#include <stdlib.h>

/* 内部：将字段添加到 cJSON 对象 */
static void temperature_report_add_to_json(const TEMPERATURE_REPORT *msg,
                                           cJSON *obj)
{
    if (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_UNIT)) {
        cJSON_AddStringToObject(obj, "unit", (const char *)msg->unit);
    }
    if (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_TEMP)) {
        cJSON_AddNumberToObject(obj, "temp", msg->temp);
    }
    if (msg->__mask__ & TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_DEVICE_ID)) {
        cJSON_AddNumberToObject(obj, "device_id", msg->device_id);
    }
}

/* 内部：从 cJSON 对象中解析字段 */
static void temperature_report_parse_from_json(TEMPERATURE_REPORT *msg,
                                               const cJSON *obj)
{
    cJSON *__item = NULL;

    __item = cJSON_GetObjectItem(obj, "unit");
    if ((NULL != __item) && cJSON_IsString(__item)) {
        strncpy((char *)msg->unit, __item->valuestring, sizeof(msg->unit) - 1);
        msg->unit[sizeof(msg->unit) - 1] = '\0';
        msg->__mask__ |= TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_UNIT);
    }

    __item = cJSON_GetObjectItem(obj, "temp");
    if ((NULL != __item) && cJSON_IsNumber(__item)) {
        msg->temp = (float)__item->valuedouble;
        msg->__mask__ |= TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_TEMP);
    }

    __item = cJSON_GetObjectItem(obj, "device_id");
    if ((NULL != __item) && cJSON_IsNumber(__item)) {
        msg->device_id = (int32_t)__item->valueint;
        msg->__mask__ |= TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_DEVICE_ID);
    }
}

/* 公共 API：JSON 序列化 */
int32_t temperature_report_serialize(const TEMPERATURE_REPORT *msg,
                                     char **json_str)
{
    cJSON *root = NULL;
    char  *out = NULL;

    if ((NULL == msg) || (NULL == json_str)) {
        return -1;
    }

    root = cJSON_CreateObject();
    if (NULL == root) {
        return -1;
    }

    temperature_report_add_to_json(msg, root);

    out = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    if (NULL == out) {
        return -1;
    }

    *json_str = out;
    return 0;
}

/* 公共 API：JSON 反序列化 */
int32_t temperature_report_deserialize(TEMPERATURE_REPORT *msg,
                                       const char *json_str)
{
    cJSON *root = NULL;

    if ((NULL == msg) || (NULL == json_str)) {
        return -1;
    }

    root = cJSON_Parse(json_str);
    if (NULL == root) {
        return -1;
    }

    temperature_report_parse_from_json(msg, root);

    cJSON_Delete(root);
    return 0;
}
```

## 7. 命令行

```bash
# 单文件
python -m protogen TemperatureReport.json -o ./generated/

# 目录批量
python -m protogen --input ./protocols/ --output ./generated/
```

参数：

| 参数 | 说明 |
|------|------|
| `--input` / `-i` | JSON 文件或目录路径 |
| `--output` / `-o` | 输出根目录（默认 `./output/`） |

行为：
- `--input` 是文件 → 生成一对 `.h/.c`
- `--input` 是目录 → 遍历目录下所有 `.json` 文件，每个生成一对 `.h/.c`
- `.h` 输出到 `{output}/inc/`，`.c` 输出到 `{output}/src/`
- 输出文件名 = 输入文件名（`TemperatureReport.json` → `temperature_report.h` / `temperature_report.c`）

输出结构：

```
generated/
├── inc/
│   ├── temperature_report.h
│   └── status_report.h
└── src/
    ├── temperature_report.c
    └── status_report.c
```

## 8. 文件规划

```
protoGen/
├── src/protogen/
│   ├── __init__.py
│   ├── parser.py          # JSON 解析 + 元字段分离
│   ├── infer.py           # 类型推导引擎 + 结构体布局
│   ├── generator.py       # C 代码生成（纯字符串拼接，零模板引擎）
│   └── cli.py             # 命令行入口
├── examples/
│   └── TemperatureReport.json
├── tests/
│   ├── test_parser.py     # 解析器测试 (4)
│   ├── test_infer.py      # 类型推导测试 (22)
│   ├── test_integration.py # 集成 + 编译测试 (5)
│   └── test_runtime.py    # C 运行时往返测试 (9)
├── docs/
│   └── design.md
├── CLAUDE.md              # AI 入职手册
├── README.md
├── pyproject.toml
└── setup.py
```
