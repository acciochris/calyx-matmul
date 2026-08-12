import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from test_gen import random_test_case


def run_test_case(case, file):
    mem_in = json.loads(case)["mem"]["data"]
    with tempfile.NamedTemporaryFile("w", suffix=".data", delete_on_close=False) as simdata:
        simdata.write(case)
        simdata.close()

        proc = subprocess.run(
            [
                "fud2",
                file,
                "-s",
                f"sim.data={simdata.name}",
                "--to",
                "dat",
                "--through",
                "icarus",
            ],
            check=True,
            capture_output=True,
        )

        json_out = json.loads(proc.stdout)

        if mem_in != json_out["memories"]["mem"]:
            raise RuntimeError("failed test case")

    return json_out["cycles"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="path to .futil file", type=Path)
    parser.add_argument("size", help="size of matrices", type=int)
    parser.add_argument("-n", help="number of test cases to run", type=int, default=10)

    args = parser.parse_args()

    exit = 0
    for i in range(args.n):
        print(f"[{i}] ", end="", file=sys.stderr)

        case = random_test_case(args.size)
        try:
            cycles = run_test_case(case=case, file=args.file)
        except Exception as e:
            print(e)
            exit = 1
            print("failed test case:", file=sys.stderr)
            print(case)
        else:
            print("passed,", cycles, "cycles", file=sys.stderr)

    if exit == 0:
        print("all passed", file=sys.stderr)
    else:
        print("some tests failed")
    return exit


if __name__ == "__main__":
    sys.exit(main())
