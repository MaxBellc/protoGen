# protoGen

JSON 报文 → C JSON 序列化/反序列化代码生成器。零外部依赖，纯 Python stdlib。

从 JSON 示例文件自动推断字段类型，生成基于 cJSON 的嵌入式 C 代码（`.h` + `.c`）。

## 特性

- **零依赖** — 纯 Python 标准库，不依赖 jinja2 等第三方包
- **类型推导** — 从 JSON 示例值自动推断 C 类型（有符号优先）
- **JSON 序列化** — 基于 cJSON，生成 `serialize(msg, &json_str)` / `deserialize(msg, json_str)` 接口
- **嵌套对象** — 递归生成子结构体，深度不限
- **对象数组** — 自动生成元素结构体 + 循环序列化
- **字段掩码** — 自动生成 `__mask__` 位掩码 + `has_` 检查函数，控制哪些字段参与序列化
- **4 字节对齐** — 尾部 `_res` 填充，大→小字段排序
- **空指针防御** — 生成的代码入口校验 `NULL`
- **编码规范** — 生成代码自动通过 clang-format，遵循项目 C 编码标准
- **pip 可安装** — `pip install .` 即可注册 `protogen` 全局命令

## 依赖

生成的 C 代码依赖 [cJSON](https://github.com/DaveGamble/cJSON) 库（编译时 `-I/path/to/cJSON -lcjson`）。

## 安装

```bash
cd protoGen
pip install -e . --break-system-packages   # 开发模式
# 或
pip install . --break-system-packages      # 正式安装
```

安装后全局可用：

```bash
protogen --input TemperatureReport.json --output ./generated/
```

## 快速开始

### 1. 编写 JSON 报文示例

```json
// TemperatureReport.json
{
  "device_id": 1234,
  "temp": 25.5,
  "unit": "Celsius",
  "__unit_size__": 16
}
```

### 2. 生成代码

```bash
protogen -i TemperatureReport.json -o ./generated/
```

输出：

```
generated/
├── inc/
│   └── temperature_report.h
└── src/
    └── temperature_report.c
```

### 3. 在 C 代码中使用

```c
#include "temperature_report.h"
#include <stdlib.h>  /* cJSON_free */

int main(void)
{
    TEMPERATURE_REPORT msg = {0};
    char *json_str = NULL;

    /* 设置要发送的字段 */
    msg.device_id = 42;
    msg.temp      = 36.5f;
    msg.__mask__  = TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_DEVICE_ID)
                  | TEMPERATURE_REPORT_MASK(TEMPERATURE_REPORT_FIELD_TEMP);

    /* 序列化为 JSON 字符串 */
    temperature_report_serialize(&msg, &json_str);
    /* json_str = "{\"device_id\":42,\"temp\":36.5}" */

    /* 反序列化 */
    TEMPERATURE_REPORT rx = {0};
    temperature_report_deserialize(&rx, json_str);

    /* 检查字段是否存在 */
    if (temperature_report_has_temp(&rx))
    {
        printf("temp = %.1f\n", rx.temp);
    }

    cJSON_free(json_str);
    return 0;
}
```

## JSON 报文格式

### 基本格式

```json
{
  "field_name": <示例值>,
  "__field_name_type__": "uint32_t",
  "__field_name_size__": 16,
  "__field_name_count__": 8,
  "__description__": "报文描述"
}
```

### 元字段

| 元字段 | 作用 | 必须 |
|--------|------|------|
| `__description__` | 消息/字段描述，写入 Doxygen | 否 |
| `__{name}_type__` | 显式指定字段 C 类型 | 否 |
| `__{name}_size__` | 字符串/bytes 缓冲区长度（向上取 2 的幂） | 否 |
| `__{name}_count__` | 数组元素个数（向上取 2 的幂） | 否 |

### 嵌套对象

```json
{
  "id": 1,
  "location": {
    "x": 10.5,
    "y": 20.3,
    "__x_type__": "double"
  }
}
```

生成子结构体 `DEVICE_REPORT_LOCATION`，包含 `x`, `y` 字段和自己的 `__mask__`。

内嵌 `__field_type__` 可覆盖子字段的类型。

### 对象数组

```json
{
  "sensor": "A",
  "readings": [
    {"temp": 25.5, "time": 1000},
    {"temp": 26.0, "time": 2000}
  ]
}
```

生成 `SENSOR_READINGS` 元素结构体，`readings` 字段类型为 `SENSOR_READINGS readings[N]`，序列化/反序列化自动生成 `for` 循环。

### 多示例增强推导

```json
{
  "examples": [
    {"device_id": 1,    "temp": 25.5, "unit": "C"},
    {"device_id": 1234, "temp": -5.0, "unit": "Fahrenheit"},
    {"device_id": 50000, "temp": 100.0, "unit": "Kelvin"}
  ]
}
```

`device_id` 范围 1~50000 → `int32_t`，`unit` 最长 10 → `uint8_t[16]`。

## 类型推导规则

默认推导为**有符号**类型。

| 示例值 | 推断类型 |
|--------|---------|
| `0` ~ `127` / 无负数 | `int8_t` |
| `128` ~ `32767` | `int16_t` |
| `32768` ~ `2147483647` | `int32_t` |
| 超出以上 | `int64_t` |
| `25.5` / `-3.14` | `float` |
| 有效数字 > 7 位 | `double` |
| `"hello"` | `uint8_t[n]`，n = 向上取 2 的幂 |
| `true` / `false` | `int8_t` |
| `[1, 2, 3]` | `int32_t[4]`，count 向上取 2 的幂 |

长度向上取 2 的幂：`3→4`, `5→8`, `9→16`, `17→32` ...

## CLI

```bash
protogen -i <JSON文件或目录> -o <输出目录>
```

| 参数 | 说明 |
|------|------|
| `-i`, `--input` | JSON 文件或目录路径（必填） |
| `-o`, `--output` | 输出根目录（默认 `./output/`） |

```bash
# 单文件
protogen -i TemperatureReport.json -o ./generated/

# 目录批量
protogen -i ./protocols/ -o ./generated/
```

## 生成的 C 代码

### 结构体

```c
typedef struct _TEMPERATURE_REPORT_
{
    uint8_t  unit[16];   /**< bit 2 — 单位字符串 */
    float    temp;       /**< bit 1 — 温度值 */
    int32_t  device_id;  /**< bit 0 — 设备ID */
    uint8_t  __mask__;   /**< 字段掩码 */
    uint8_t  _res1[3];   /**< 4 字节对齐保留 */
} TEMPERATURE_REPORT;
```

- 字段**大→小排序**（降低对齐填充）
- 尾部自动补 `_res1`, `_res2` ... 至 4 字节对齐
- `__mask__` 类型按字段数自动选择：≤8 → `uint8_t`，≤16 → `uint16_t`，≤32 → `uint32_t`

### 字段枚举 + MASK 宏

```c
enum {
    TEMPERATURE_REPORT_FIELD_DEVICE_ID = 0,
    TEMPERATURE_REPORT_FIELD_TEMP      = 1,
    TEMPERATURE_REPORT_FIELD_UNIT      = 2,
};

#define TEMPERATURE_REPORT_MASK(field)  (1u << (field))
```

### API

```c
/* JSON 序列化：msg → JSON 字符串（调用者需 cJSON_free 释放 *json_str） */
int32_t temperature_report_serialize(const TEMPERATURE_REPORT *msg,
                                     char **json_str);

/* JSON 反序列化：JSON 字符串 → msg */
int32_t temperature_report_deserialize(TEMPERATURE_REPORT *msg,
                                       const char *json_str);

/* 掩码检查 */
int32_t temperature_report_has_device_id(const TEMPERATURE_REPORT *msg);
int32_t temperature_report_has_temp(const TEMPERATURE_REPORT *msg);
int32_t temperature_report_has_unit(const TEMPERATURE_REPORT *msg);
```

### 安全保证

- `serialize`：`msg`/`json_str` 任一为 `NULL` 返回 `-1`；`cJSON_CreateObject` 失败返回 `-1`
- `deserialize`：`msg`/`json_str` 为 `NULL` 返回 `-1`；JSON 解析失败返回 `-1`
- `has_`：`msg` 为 `NULL` 返回 `0`
- 生成代码**不分配内存**（零 `malloc`），JSON 字符串由 cJSON 内部分配，调用者负责 `cJSON_free`
- 反序列化使用 `strncpy` 防字符串溢出，数值数组有越界保护

## 文件结构

```
protoGen/
├── src/protogen/
│   ├── __init__.py
│   ├── parser.py          # JSON 解析 + 元字段分离
│   ├── infer.py           # 类型推导 + 结构体布局
│   ├── generator.py       # C 代码生成（纯字符串拼接）
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
├── pyproject.toml
├── setup.py
└── README.md
```

## 测试

```bash
cd protoGen
PYTHONPATH=src python3 -m unittest tests.test_parser tests.test_infer tests.test_integration tests.test_runtime -v

# Ran 40 tests — OK
```

## 编码规范

生成的代码遵循项目 [coding_style](../coding_style/CODING_STYLE.md)：

- Yoda 条件、Allman 括号、4 空格缩进、80 列
- 定宽类型 (`int32_t` 而非 `int`)
- `typedef struct _UPPER_CASE_ { ... } UPPER_CASE;`
- Doxygen `@param[in]` / `@param[out]` / `@return`
- `void` 函数显式 `return;`
- 函数顶部声明变量并初始化
- 自动通过 clang-format 格式化

## 灵感

设计灵感来源于 [Protocol Buffers](https://protobuf.dev/)，针对嵌入式 C 场景做了精简：

- JSON 替代 `.proto` 描述文件，无需编译器插件
- 基于 cJSON 的标准 JSON 序列化，人可读、跨语言互通
- 字段掩码实现可选字段，类似 `optional` 语义
- 零依赖纯 Python 代码生成，替代 `protoc`

## 许可

MIT
