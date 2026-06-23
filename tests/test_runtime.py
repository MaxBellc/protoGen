"""生成的 C JSON 代码运行时测试。"""
import json, os, subprocess, sys, tempfile, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from protogen.parser import parse_file
from protogen.infer import infer_fields, layout_struct
from protogen.generator import generate_one

CJSON_INC = os.environ.get("CJSON_INC", "/usr/local/include")
CJSON_LIB = os.environ.get("CJSON_LIB", "/usr/local/lib/libcjson.a")


def _gen_compile(tmpdir, name, data):
    """生成代码并编译为 .o，返回 (inc_dir, obj_path)。"""
    jp = os.path.join(tmpdir, f"{name}.json")
    with open(jp, "w") as f:
        json.dump(data, f)
    msg = parse_file(jp)
    fields = infer_fields(msg["fields"])
    layout = layout_struct(fields)
    out = os.path.join(tmpdir, "gen")
    h_path, c_path = generate_one(msg, layout, out)
    inc = os.path.dirname(h_path)
    obj = os.path.join(tmpdir, f"{name}.o")
    r = subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-c", c_path,
         "-I", inc, "-I", CJSON_INC, "-o", obj], capture_output=True, text=True)
    assert r.returncode == 0, f"compile: {r.stderr}"
    return inc, obj


def _run(tmpdir, obj, inc, source):
    """链接 cJSON + 运行 C 测试程序，返回 stdout。"""
    tc = os.path.join(tmpdir, "test_main.c")
    exe = os.path.join(tmpdir, "test_exe")
    with open(tc, "w") as f:
        f.write(source)
    r = subprocess.run(
        ["gcc", "-std=c11", "-Wall", "-Wextra", "-Werror",
         tc, obj, "-I", inc, "-I", CJSON_INC, CJSON_LIB, "-lm",
         "-o", exe], capture_output=True, text=True)
    assert r.returncode == 0, f"link: {r.stderr}"
    r = subprocess.run([exe], capture_output=True, text=True)
    assert r.returncode == 0, f"run: {r.stdout}{r.stderr}"
    return r.stdout


class TestRuntime(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    # ---- 基本 JSON 往返 ----

    def test_round_trip_all(self):
        inc, obj = _gen_compile(self.tmp, "Sensor",
                                {"id": 1234, "temp": 25.5, "name": "s1"})
        out = _run(self.tmp, obj, inc, """
#include "sensor.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int main(void) {
    SENSOR src = {0}, dst = {0};
    char *js = NULL;
    src.id = 42; src.temp = 36.5f;
    strcpy((char*)src.name, "OK");
    src.__mask__ = SENSOR_MASK(SENSOR_FIELD_ID)
                 | SENSOR_MASK(SENSOR_FIELD_TEMP)
                 | SENSOR_MASK(SENSOR_FIELD_NAME);
    if (0 != sensor_serialize(&src, &js)) return 1;
    if (0 != sensor_deserialize(&dst, js)) return 2;
    if (dst.id != 42) return 3;
    if (dst.temp != 36.5f) return 4;
    if (strcmp((char*)dst.name, "OK") != 0) return 5;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    def test_partial_mask(self):
        inc, obj = _gen_compile(self.tmp, "Part",
                                {"a": 1, "b": 2, "c": 3})
        out = _run(self.tmp, obj, inc, """
#include "part.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int main(void) {
    PART src = {0}, dst = {0};
    char *js = NULL;
    src.a = 10; src.b = 20;
    src.__mask__ = PART_MASK(PART_FIELD_A) | PART_MASK(PART_FIELD_B);
    if (0 != part_serialize(&src, &js)) return 1;
    if (0 != part_deserialize(&dst, js)) return 2;
    if (dst.a != 10) return 3;
    if (dst.b != 20) return 4;
    if (part_has_c(&dst)) return 5;
    if (!part_has_a(&dst)) return 6;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    # ---- 嵌套对象 ----

    def test_nested_round_trip(self):
        """嵌套对象 JSON 序列化/反序列化 往返。"""
        inc, obj = _gen_compile(self.tmp, "Dev",
                                {"id": 1, "loc": {"x": 10.5, "y": 20.3}})
        out = _run(self.tmp, obj, inc, """
#include "dev.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    DEV src = {0}, dst = {0};
    char *js = NULL;
    src.id = 99;
    src.loc.x = 1.5f; src.loc.y = 2.5f;
    src.loc.__mask__ = DEV_LOC_MASK(DEV_LOC_FIELD_X)
                     | DEV_LOC_MASK(DEV_LOC_FIELD_Y);
    src.__mask__ = DEV_MASK(DEV_FIELD_LOC)
                 | DEV_MASK(DEV_FIELD_ID);
    if (0 != dev_serialize(&src, &js)) return 1;
    if (0 != dev_deserialize(&dst, js)) return 2;
    if (dst.id != 99) return 3;
    if (dst.loc.x != 1.5f) return 4;
    if (dst.loc.y != 2.5f) return 5;
    if (!dev_has_loc(&dst)) return 6;
    if (!dev_has_id(&dst)) return 7;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    def test_nested_partial_mask(self):
        """嵌套对象 — 部分字段传输。"""
        inc, obj = _gen_compile(self.tmp, "Dev2",
                                {"id": 1, "loc": {"x": 10.5, "y": 20.3}})
        out = _run(self.tmp, obj, inc, """
#include "dev2.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    DEV2 src = {0}, dst = {0};
    char *js = NULL;
    src.id = 77;
    src.loc.x = 3.0f;
    src.loc.__mask__ = DEV2_LOC_MASK(DEV2_LOC_FIELD_X);
    /* 只传 loc.x 和 id，不传 loc.y */
    src.__mask__ = DEV2_MASK(DEV2_FIELD_LOC)
                 | DEV2_MASK(DEV2_FIELD_ID);
    if (0 != dev2_serialize(&src, &js)) return 1;
    if (0 != dev2_deserialize(&dst, js)) return 2;
    if (dst.id != 77) return 3;
    if (dst.loc.x != 3.0f) return 4;
    if (dst.loc.y != 0.0f) return 5;  /* 未被传输，保持 0 */
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    # ---- 深层嵌套 ----

    def test_deep_nested_round_trip(self):
        """深层嵌套(2+层) — JSON 往返测试。"""
        inc, obj = _gen_compile(self.tmp, "Deep2",
                                {"id": 1, "outer": {"inner": {"val": 42}, "flag": True}})
        out = _run(self.tmp, obj, inc, """
#include "deep2.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    DEEP2 src = {0}, dst = {0};
    char *js = NULL;
    src.id = 55;
    src.outer.inner.val = 123;
    src.outer.inner.__mask__ = DEEP2_OUTER_INNER_MASK(DEEP2_OUTER_INNER_FIELD_VAL);
    src.outer.flag = 1;
    src.outer.__mask__ = DEEP2_OUTER_MASK(DEEP2_OUTER_FIELD_INNER)
                       | DEEP2_OUTER_MASK(DEEP2_OUTER_FIELD_FLAG);
    src.__mask__ = DEEP2_MASK(DEEP2_FIELD_OUTER)
                 | DEEP2_MASK(DEEP2_FIELD_ID);
    if (0 != deep2_serialize(&src, &js)) return 1;
    if (0 != deep2_deserialize(&dst, js)) return 2;
    if (dst.id != 55) return 3;
    if (dst.outer.inner.val != 123) return 4;
    if (dst.outer.flag != 1) return 5;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    # ---- 同名字段 ----

    def test_nested_same_name_fields(self):
        """父/子同名字段 — 不冲突。"""
        inc, obj = _gen_compile(self.tmp, "Same",
                                {"id": 1, "name": "parent",
                                 "child": {"id": 42, "name": "child_name"}})
        out = _run(self.tmp, obj, inc, """
#include "same.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
int main(void) {
    SAME src = {0}, dst = {0};
    char *js = NULL;
    src.id = 10;
    strcpy((char*)src.name, "P");
    src.child.id = 20;
    strcpy((char*)src.child.name, "C");
    src.child.__mask__ = SAME_CHILD_MASK(SAME_CHILD_FIELD_ID)
                       | SAME_CHILD_MASK(SAME_CHILD_FIELD_NAME);
    src.__mask__ = SAME_MASK(SAME_FIELD_CHILD)
                 | SAME_MASK(SAME_FIELD_ID)
                 | SAME_MASK(SAME_FIELD_NAME);
    if (0 != same_serialize(&src, &js)) return 1;
    if (0 != same_deserialize(&dst, js)) return 2;
    if (dst.id != 10) return 3;
    if (strcmp((char*)dst.name, "P") != 0) return 4;
    if (dst.child.id != 20) return 5;
    if (strcmp((char*)dst.child.name, "C") != 0) return 6;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    # ---- 对象数组 ----

    def test_array_of_objects_round_trip(self):
        """对象数组 — JSON 往返测试。"""
        inc, obj = _gen_compile(self.tmp, "Sensor2",
                                {"readings": [
                                    {"temp": 10.0, "time": 100},
                                    {"temp": 20.0, "time": 200},
                                ]})
        out = _run(self.tmp, obj, inc, """
#include "sensor2.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    SENSOR2 src = {0}, dst = {0};
    char *js = NULL;
    src.readings[0].temp = 15.5f; src.readings[0].time = 111;
    src.readings[0].__mask__ = SENSOR2_READINGS_MASK(SENSOR2_READINGS_FIELD_TEMP)
                             | SENSOR2_READINGS_MASK(SENSOR2_READINGS_FIELD_TIME);
    src.readings[1].temp = 25.5f; src.readings[1].time = 222;
    src.readings[1].__mask__ = SENSOR2_READINGS_MASK(SENSOR2_READINGS_FIELD_TEMP)
                             | SENSOR2_READINGS_MASK(SENSOR2_READINGS_FIELD_TIME);
    src.__mask__ = SENSOR2_MASK(SENSOR2_FIELD_READINGS);
    if (0 != sensor2_serialize(&src, &js)) return 1;
    if (0 != sensor2_deserialize(&dst, js)) return 2;
    if (dst.readings[0].temp != 15.5f) return 3;
    if (dst.readings[0].time != 111) return 4;
    if (dst.readings[1].temp != 25.5f) return 5;
    if (dst.readings[1].time != 222) return 6;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    # ---- 防御测试 ----

    def test_null_defense(self):
        inc, obj = _gen_compile(self.tmp, "Nt", {"value": 1})
        out = _run(self.tmp, obj, inc, """
#include "nt.h"
#include <stdio.h>
#include <stdlib.h>
int main(void) {
    NT msg; char *js = NULL;
    if (nt_serialize(NULL, &js) != -1) return 1;
    if (nt_deserialize(NULL, "{}") != -1) return 2;
    if (nt_serialize(&msg, NULL) != -1) return 3;
    if (nt_deserialize(&msg, NULL) != -1) return 4;
    if (nt_deserialize(&msg, "not json") != -1) return 5;
    if (nt_has_value(NULL) != 0) return 6;
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)

    # ---- 部分 mask JSON —— 未传输字段不出现在 JSON 中 ----

    def test_json_partial_mask(self):
        """JSON 部分字段 mask — 无需传输的字段不出现在 JSON 中。"""
        inc, obj = _gen_compile(self.tmp, "J2",
                                {"a": 1, "b": 1000, "c": 3})
        out = _run(self.tmp, obj, inc, """
#include "j2.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void) {
    J2 src = {0}, dst = {0};
    char *js = NULL;
    src.a = 100; src.b = 200;
    src.__mask__ = J2_MASK(J2_FIELD_A) | J2_MASK(J2_FIELD_B);
    /* c 不在 mask 中 */
    if (0 != j2_serialize(&src, &js)) return 1;
    /* JSON 不应包含 "c" 键 */
    if (NULL != strstr(js, "\\\"c\\\"")) return 2;
    if (0 != j2_deserialize(&dst, js)) return 3;
    if (dst.a != 100) return 4;
    if (dst.b != 200) return 5;
    if (j2_has_c(&dst)) return 6;
    cJSON_free(js);
    printf("PASS\\n"); return 0;
}
""")
        self.assertIn("PASS", out)


if __name__ == "__main__":
    unittest.main()
