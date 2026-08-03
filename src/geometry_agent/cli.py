"""Command-line entry point."""
from __future__ import annotations

import argparse
import sys

from .pipeline import solve
from .types import GradeLevel, SolveRequest


def main() -> int:
    ap = argparse.ArgumentParser(prog="geometry-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_solve = sub.add_parser("solve", help="solve a geometry problem")
    p_solve.add_argument("--image", default="", help="path to the problem image (optional for text-only)")
    p_solve.add_argument("--text", required=True, help="problem text")
    p_solve.add_argument("--grade", choices=["junior", "senior", "competition"], default="senior",
                         help="学段级别: junior(初中) / senior(高中) / competition(竞赛)。"
                              "平面几何支持全部三级; 解析几何支持 senior/competition; "
                              "立体几何仅 senior; 函数导数支持 senior/competition。"
                              "不兼容时系统自动升级并提示。工具集不变。")
    p_solve.add_argument("--config", default=None)
    p_solve.add_argument("--out", default="-")

    args = ap.parse_args()
    if args.cmd == "solve":
        grade = GradeLevel(args.grade)
        req = SolveRequest(
            image_path=args.image,
            problem_text=args.text,
            grade=grade,
        )
        resp = solve(req)
        if resp.error:
            print(f"Error: {resp.error}", file=sys.stderr)
            return 1
        out = resp.model_dump_json(indent=2)
        if args.out == "-":
            print(out)
        else:
            with open(args.out, "w") as f:
                f.write(out)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
