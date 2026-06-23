"""命令行入口。"""

import argparse
import os
import sys

from protogen.parser import parse_file
from protogen.infer import infer_fields, layout_struct
from protogen.generator import generate_one


def main():
    parser = argparse.ArgumentParser(
        description="protoGen — JSON 报文 → C JSON 序列化代码生成器"
    )
    parser.add_argument(
        "-i", "--input", required=True,
        help="JSON 文件或目录路径"
    )
    parser.add_argument(
        "-o", "--output", default="./output/",
        help="输出根目录 (默认 ./output/)"
    )
    args = parser.parse_args()

    input_path = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)

    if not os.path.exists(input_path):
        print(f"错误: 输入路径不存在: {input_path}", file=sys.stderr)
        sys.exit(1)

    # 收集 JSON 文件
    json_files = []
    if os.path.isfile(input_path):
        json_files = [input_path]
    elif os.path.isdir(input_path):
        for f in sorted(os.listdir(input_path)):
            if f.endswith(".json"):
                json_files.append(os.path.join(input_path, f))

    if not json_files:
        print("错误: 未找到 JSON 文件", file=sys.stderr)
        sys.exit(1)

    # 逐个处理
    for filepath in json_files:
        print(f"处理: {os.path.basename(filepath)}")
        msg_info = parse_file(filepath)
        fields = infer_fields(msg_info["fields"])
        layout = layout_struct(fields)
        h_path, c_path = generate_one(msg_info, layout, output_dir)
        print(f"  → {h_path}")
        print(f"  → {c_path}")

    print(f"\n生成完成: {len(json_files)} 个消息")


if __name__ == "__main__":
    main()
