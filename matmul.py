import argparse
import sys
from pathlib import Path

import calyx.builder as cb
from calyx import py_ast as ast


def comb_mem_d3(
    comp: cb.ComponentBuilder,
    name: str,
    bitwidth: int,
    size0: int,
    size1: int,
    size2: int,
    idx_size0: int,
    idx_size1: int,
    idx_size2: int,
    is_external: bool = False,
    is_ref: bool = False,
) -> cb.CellBuilder:
    comp.prog.import_("primitives/memories/comb.futil")
    return comp.cell(
        name,
        ast.Stdlib.comb_mem_d3(
            bitwidth=bitwidth,
            size0=size0,
            size1=size1,
            size2=size2,
            idx_size0=idx_size0,
            idx_size1=idx_size1,
            idx_size2=idx_size2,
        ),
        is_external=is_external,
        is_ref=is_ref,
    )


def matmul_inner_nxn(prog: cb.Builder, n: int = 2, bitwidth: int = 32):
    """Generate a matrix multiplication unit with a basic triple-looping inner product"""

    comp = prog.component("main")

    # input: two 2x2 matrices at index 0 and 1
    # output: one 2x2 matrix at index 2
    idx_size = n.bit_length()
    mem = comb_mem_d3(
        comp,
        "mem",
        bitwidth=bitwidth,
        size0=3,
        size1=n,
        size2=n,
        idx_size0=2,
        idx_size1=idx_size,
        idx_size2=idx_size,
        is_external=True,
    )

    # indices
    i = comp.reg(idx_size)
    j = comp.reg(idx_size)
    k = comp.reg(idx_size)

    # temp registers
    reg0 = comp.reg(bitwidth)
    reg1 = comp.reg(bitwidth)
    reg2 = comp.reg(bitwidth)

    mult_pipe = comp.mult_pipe(bitwidth)
    add = comp.add(bitwidth)

    with comp.group("read_mat_0") as read_mat_0:
        mem.addr0 = cb.const(2, 0)
        mem.addr1 = i.out
        mem.addr2 = k.out
        reg0.in_ = mem.read_data
        reg0.write_en = cb.HI
        read_mat_0.done = reg0.done

    with comp.group("read_mat_1") as read_mat_1:
        mem.addr0 = cb.const(2, 1)
        mem.addr1 = k.out
        mem.addr2 = j.out
        reg1.in_ = mem.read_data
        reg1.write_en = cb.HI
        read_mat_1.done = reg1.done

    with comp.group("mult_and_add") as mult_and_add:
        mult_pipe.left = reg0.out
        mult_pipe.right = reg1.out
        add.left = mult_pipe.out
        add.right = reg2.out
        reg2.in_ = mult_pipe.done @ add.out
        reg2.write_en = mult_pipe.done
        mult_pipe.go = cb.HI
        mult_and_add.done = reg2.done

    with comp.group("write_result") as write_result:
        mem.addr0 = cb.const(2, 2)
        mem.addr1 = i.out
        mem.addr2 = j.out
        mem.write_data = reg2.out
        mem.write_en = cb.HI
        write_result.done = mem.done

    comp.control += [
        comp.reg_store(i, 0),
        cb.while_with(
            comp.lt_use(i.out, n),
            [
                comp.reg_store(j, 0),
                cb.while_with(
                    comp.lt_use(j.out, n),
                    [
                        comp.reg_store(k, 0),
                        comp.reg_store(reg2, 0),
                        cb.while_with(
                            comp.lt_use(k.out, n),
                            [
                                read_mat_0,
                                read_mat_1,
                                mult_and_add,
                                comp.incr(k),
                            ],
                        ),
                        write_result,
                        comp.incr(j),
                    ],
                ),
                comp.incr(i),
            ],
        ),
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("size", help="size of the square matrix", default=2, type=int)
    args = parser.parse_args()

    prog = cb.Builder(str(Path(__file__).resolve().parent))
    matmul_inner_nxn(prog, args.size)
    prog.program.emit()


if __name__ == "__main__":
    sys.exit(main())
