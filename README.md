# calyx-matmul

Hardware matrix multiplication unit with [Calyx](https://calyxir.org/).

There is a [writeup](writeup.md) explaining the steps I took to implement this. To run the code,
Calyx needs to be built from source following the [instructions](https://docs.calyxir.org/).
Then make sure that this repository is cloned alongside Calyx such that `../calyx/calyx-py`
relative to this README points to the Calyx Python library.

To run the inner product (triple while loop) compiler:

```
uv run inner/matmul.py <matrix dimension> > /path/to/output.futil
```

To run the systolic array compiler:

```
uv run systolic/systolic.py <matrix dimension> (--static) > /path/to/output.futil
```

(the `--static` flag is to enable static timing)

To run tests, execute

```
uv run tests/run_tests.py /path/to/calyx_ir.futil <matrix dimension>
```
