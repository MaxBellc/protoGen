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

---

## 编写协议模板

### 单文件模板

一个 JSON 文件定义一条消息。文件名即为消息名（`SensorData.json` → `SENSOR_DATA`）。

**示例：温湿度传感器上报**

```json
{
  "device_id": 1001,
  "temperature": 25.5,
  "humidity": 68.2,
  "location": "living_room",
  "__location_size__": 32
}
```

**示例：设备状态（含嵌套对象）**

```json
{
  "device_id": 1,
  "status": {
    "power": true,
    "battery": 85,
    "signal": -42,
    "__power_type__": "int8_t"
  },
  "timestamp": 1700000000,
  "__timestamp_type__": "uint32_t"
}
```

**示例：GPS 轨迹（含对象数组）**

```json
{
  "device_id": 1001,
  "waypoints": [
    {"lat": 31.2304, "lon": 121.4737},
    {"lat": 31.2350, "lon": 121.4800},
    {"lat": 31.2400, "lon": 121.4850}
  ]
}
```

生成子结构体 `GPS_TRACK_WAYPOINTS`（每个元素的类型），waypoints 字段类型为 `GPS_TRACK_WAYPOINTS waypoints[4]`。数组长度按示例元素数 3 → 向上取 2 的幂 → 4。

序列化和反序列化时自动生成 `for` 循环遍历数组，每个元素调用子结构体的 JSON 构建/解析函数。

### 模板写法规则

| 规则 | 说明 |
|------|------|
| 字段值决定类型 | 写 `25.5` → 得到 `float`，写 `1000` → 得到 `int16_t` |
| 字符串缓冲 | 默认按示例字符串长度向上取 2 的幂。`"hello"` (5 字节) → `uint8_t[8]` |
| 显式指定大小 | `"__field_size__": 32` → 强制 `uint8_t[32]` |
| 显式指定类型 | `"__field_type__": "double"` → 覆盖自动推导 |
| 布尔值 | 写 `true` / `false` → 得到 `int8_t` (0/1) |
| 数组长度 | 按示例元素数向上取 2 的幂，`"__field_count__": 10` → `[16]` |
| 元字段命名 | `__` 开头 + `__` 结尾，嵌在数据字段之间 |
| 隐藏字段 | 不想生成某个字段的代码 → `"__field_hidden__": true` |

### 目录批量定义

将多个 `.json` 文件放入同一目录，一次生成所有消息：

```
protocols/
├── SensorData.json          → sensor_data.h / sensor_data.c
├── DeviceStatus.json        → device_status.h / device_status.c
└── ControlCommand.json      → control_command.h / control_command.c
```

```bash
protogen -i ./protocols/ -o ./generated/
```

---

## 自动化编译

生成的代码需要链接 cJSON 库。以下是集成到 CMake 项目的完整方案。

### 项目结构（推荐）

```
my_project/
├── protocols/                # protoGen 输入的 JSON 模板
│   ├── SensorData.json
│   └── DeviceStatus.json
├── generated/                # protoGen 输出（可加入 .gitignore）
│   ├── inc/
│   │   ├── sensor_data.h
│   │   └── device_status.h
│   └── src/
│       ├── sensor_data.c
│       └── device_status.c
├── src/                      # 你的业务代码
│   └── main.c
├── CMakeLists.txt
└── Makefile                  # （可选）便捷脚本
```

### CMakeLists.txt

```cmake
cmake_minimum_required(VERSION 3.10)
project(my_project VERSION 1.0.0 LANGUAGES C)

# protoGen 生成目录 + cJSON 头文件路径
set(GENERATED_DIR ${CMAKE_CURRENT_SOURCE_DIR}/generated)
set(CJSON_DIR     ${CMAKE_CURRENT_SOURCE_DIR}/../cJSON)

# 可执行文件
add_executable(my_app
    src/main.c
    ${GENERATED_DIR}/src/sensor_data.c
    ${GENERATED_DIR}/src/device_status.c
    ${CJSON_DIR}/cJSON.c
)

target_include_directories(my_app PRIVATE
    ${GENERATED_DIR}/inc
    ${CJSON_DIR}
)

target_compile_options(my_app PRIVATE
    -Wall -Wextra -Werror
    -Wdeclaration-after-statement
    -std=c11
)
```

### Makefile（便捷包装）

```makefile
.PHONY: proto build clean run

# 从 JSON 模板生成 C 代码
proto:
	protogen -i ./protocols/ -o ./generated/

# 编译
build:
	gcc -std=c11 -Wall -Wextra -Werror \
	    -I ./generated/inc \
	    -I ../cJSON \
	    src/main.c \
	    generated/src/*.c \
	    ../cJSON/cJSON.c \
	    -o build/my_app \
	    -lm

# 一键：生成 + 编译 + 运行
all: proto build run

run:
	./build/my_app

clean:
	rm -rf build/ generated/
```

### 编译脚本（纯 shell，无需 Make）

```bash
#!/bin/bash
set -e

# 1. 生成 C 代码
protogen -i ./protocols/ -o ./generated/

# 2. 编译
gcc -std=c11 -Wall -Wextra -Werror \
    -I ./generated/inc \
    -I ../cJSON \
    src/main.c \
    generated/src/*.c \
    ../cJSON/cJSON.c \
    -o build/my_app \
    -lm

# 3. 运行
./build/my_app
```

### 交叉编译（aarch64 / 嵌入式 Linux）

```bash
# 先设置交叉编译器路径
export CC=aarch64-linux-gnu-gcc

# 生成代码（protoGen 本身是 Python，始终在 host 上跑）
protogen -i ./protocols/ -o ./generated/

# 交叉编译
${CC} -std=c11 -Wall -Wextra -Werror \
    -I ./generated/inc \
    -I ../cJSON \
    src/main.c \
    generated/src/*.c \
    ../cJSON/cJSON.c \
    -o build/my_app \
    -lm -static
```

---

## 完整工作流示例

下面从零开始做一个温湿度传感器上报的完整流程。

### Step 1: 写 JSON 模板

```json
// protocols/SensorData.json
{
  "device_id": 1,
  "temperature": 25.5,
  "humidity": 60.0,
  "location": "room-01",
  "__location_size__": 32
}
```

### Step 2: 生成代码

```bash
protogen -i protocols/SensorData.json -o generated/
```

### Step 3: 写业务代码

```c
// src/main.c
#include "sensor_data.h"
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    /* ---- 序列化 ---- */
    SENSOR_DATA msg = {0};

    msg.device_id   = 42;
    msg.temperature = 25.5;
    msg.humidity    = 68.2;
    snprintf((char *)msg.location, sizeof(msg.location), "living_room");

    /* 只传温度、湿度和位置，不传 device_id */
    msg.__mask__ = SENSOR_DATA_MASK(SENSOR_DATA_FIELD_TEMPERATURE)
                 | SENSOR_DATA_MASK(SENSOR_DATA_FIELD_HUMIDITY)
                 | SENSOR_DATA_MASK(SENSOR_DATA_FIELD_LOCATION);

    char *json_str = NULL;
    sensor_data_serialize(&msg, &json_str);
    printf("序列化: %s\n", json_str);
    /* 输出: {"temperature":25.5,"humidity":68.2,"location":"living_room"} */

    /* ---- 反序列化 ---- */
    SENSOR_DATA rx = {0};
    sensor_data_deserialize(&rx, json_str);

    if (sensor_data_has_temperature(&rx))
    {
        printf("温度 = %.1f\n", rx.temperature);
    }
    if (sensor_data_has_device_id(&rx))
    {
        printf("设备ID = %d\n", rx.device_id);
    }
    else
    {
        printf("设备ID 未传输\n");
    }

    cJSON_free(json_str);
    return 0;
}
```

### Step 4: 编译运行

```bash
gcc -std=c11 -Wall -Wextra -Werror \
    -I generated/inc -I ../cJSON \
    src/main.c generated/src/sensor_data.c ../cJSON/cJSON.c \
    -o build/sensor_demo -lm

./build/sensor_demo
```

### 在 MQTT 场景中使用

```c
#include "mqtt_client.h"
#include "sensor_data.h"

void publish_sensor(MQTT_CLIENT *client)
{
    SENSOR_DATA msg = {0};
    char       *json_str = NULL;

    /* 读取传感器数据 */
    msg.device_id   = get_device_id();
    msg.temperature = read_temperature();
    msg.humidity    = read_humidity();
    msg.__mask__    = SENSOR_DATA_MASK(SENSOR_DATA_FIELD_DEVICE_ID)
                    | SENSOR_DATA_MASK(SENSOR_DATA_FIELD_TEMPERATURE)
                    | SENSOR_DATA_MASK(SENSOR_DATA_FIELD_HUMIDITY);

    /* 序列化 + 发布 */
    sensor_data_serialize(&msg, &json_str);

    /* 构造 cJSON 对象用于 mqttClient API */
    cJSON *payload = cJSON_Parse(json_str);
    mqtt_client_publish(client, "sensor/data", payload, 1, 0);

    cJSON_Delete(payload);
    cJSON_free(json_str);
}
```

### 对象数组的使用

```c
#include "gps_track.h"

void send_gps_track(MQTT_CLIENT *client)
{
    GPS_TRACK msg = {0};
    char     *json_str = NULL;

    /* 填充第一条轨迹点 */
    msg.waypoints[0].lat = 31.2304;
    msg.waypoints[0].lon = 121.4737;
    msg.waypoints[0].__mask__ = GPS_TRACK_WAYPOINTS_MASK(
                                    GPS_TRACK_WAYPOINTS_FIELD_LAT)
                              | GPS_TRACK_WAYPOINTS_MASK(
                                    GPS_TRACK_WAYPOINTS_FIELD_LON);

    /* 填充第二条轨迹点 */
    msg.waypoints[1].lat = 31.2350;
    msg.waypoints[1].lon = 121.4800;
    msg.waypoints[1].__mask__ = GPS_TRACK_WAYPOINTS_MASK(
                                    GPS_TRACK_WAYPOINTS_FIELD_LAT)
                              | GPS_TRACK_WAYPOINTS_MASK(
                                    GPS_TRACK_WAYPOINTS_FIELD_LON);

    /* 只传 waypoints，不传 device_id */
    msg.__mask__ = GPS_TRACK_MASK(GPS_TRACK_FIELD_WAYPOINTS);

    /* 序列化 → 发布 */
    gps_track_serialize(&msg, &json_str);
    /* {"waypoints":[{"lat":31.2304,"lon":121.4737},{"lat":31.235,"lon":121.48}]} */

    cJSON *payload = cJSON_Parse(json_str);
    mqtt_client_publish(client, "gps/track", payload, 1, 0);

    cJSON_Delete(payload);
    cJSON_free(json_str);
}
```

### 反序列化对象数组

```c
GPS_TRACK rx = {0};
gps_track_deserialize(&rx, json_str);

/* 遍历已传输的轨迹点 */
for (int32_t i = 0; i < 4; i++)
{
    if (gps_track_has_waypoints(&rx))
    {
        printf("waypoint[%d]: lat=%.4f lon=%.4f\n",
               i, rx.waypoints[i].lat, rx.waypoints[i].lon);
    }
}
```

---

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
