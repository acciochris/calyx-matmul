import argparse
import json
import random


def random_matrix(size):
    mat = []
    for _ in range(size):
        mat.append([random.randrange(100) for _ in range(size)])
    return mat


def random_test_case(size):
    TEMPLATE = {
        "mem": {
            "data": [],
            "format": {"numeric_type": "bitnum", "is_signed": False, "width": 32},
        }
    }

    TEMPLATE["mem"]["data"].append(random_matrix(size))
    TEMPLATE["mem"]["data"].append(random_matrix(size))
    TEMPLATE["mem"]["data"].append(
        [[0 for _ in range(size)] for _ in range(size)]
    )

    for i in range(size):
        for j in range(size):
            TEMPLATE["mem"]["data"][2][i][j] = sum(
                [
                    TEMPLATE["mem"]["data"][0][i][k] * TEMPLATE["mem"]["data"][1][k][j]
                    for k in range(size)
                ]
            )

    return json.dumps(TEMPLATE)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("size", help="size of the square matrix", default=2, type=int)
    args = parser.parse_args()
    print(random_test_case(args.size))
