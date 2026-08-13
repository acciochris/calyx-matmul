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


def sguard(start: int, stop: int | None = None) -> cb.ExprBuilder:
    """Create a static cycle guard"""

    guard = ast.GuardExpr()
    guard.doc = lambda: f"%[{start}:{stop}]" if stop else f"%{start}"
    return cb.ExprBuilder(guard)


def define_pe(comp: cb.ComponentBuilder, bitwidth: int = 32, static: bool = False):
    comp.input("ain", bitwidth)
    comp.input("bin", bitwidth)
    comp.input("clear", 1)
    comp.output("aout", bitwidth)
    comp.output("bout", bitwidth)
    comp.output("out", bitwidth)
    this = comp.this()

    mult_pipe = comp.mult_pipe(bitwidth, "mult_pipe")
    add = comp.add(bitwidth, "add")
    a = comp.reg(bitwidth, "a")
    b = comp.reg(bitwidth, "b")
    result = comp.reg(bitwidth, "result")

    with comp.continuous:
        this.out = result.out
        this.aout = a.out
        this.bout = b.out

    if static:
        group_1 = lambda x: comp.static_group(x, latency=1)
    else:
        group_1 = comp.group

    comp.group = group_1  # type: ignore

    with group_1("store_a") as store_a:
        a.in_ = ~this.clear @ this.ain
        a.in_ = this.clear @ 0
        a.write_en = 1
        if not static:
            store_a.done = a.done

    with group_1("store_b") as store_b:
        b.in_ = ~this.clear @ this.bin
        b.in_ = this.clear @ 0
        b.write_en = 1
        if not static:
            store_b.done = b.done

    if static:
        with comp.static_group("mult_and_add", latency=4) as mult_and_add:
            mult_pipe.left = sguard(0, 3) @ a.out
            mult_pipe.right = sguard(0, 3) @ b.out
            mult_pipe.go = sguard(0, 3) @ cb.HI
            add.left = result.out
            add.right = mult_pipe.out
            result.in_ = (~this.clear & sguard(3)) @ add.out
            result.in_ = this.clear @ 0
            result.write_en = sguard(3) @ cb.HI
    else:
        with comp.group("mult_and_add") as mult_and_add:
            mult_pipe.left = a.out
            mult_pipe.right = b.out
            mult_pipe.go = cb.HI
            add.left = result.out
            add.right = mult_pipe.out
            result.in_ = (~this.clear & mult_pipe.done) @ add.out
            result.in_ = this.clear @ 0
            result.write_en = mult_pipe.done
            mult_and_add.done = result.done

    if static:
        comp.control += cb.static_seq(
            cb.static_par(
                store_a,
                store_b,
            ),
            mult_and_add,
        )
    else:
        comp.control += [
            cb.par(
                store_a,
                store_b,
            ),
            mult_and_add,
        ]


def matmul_systolic_nxn(
    prog: cb.Builder, n: int = 2, bitwidth: int = 32, static: bool = False
):
    """Generate a matrix multiplication unit with a basic triple-looping inner product"""

    pe_comp = prog.component("pe", latency=5 if static else None)
    define_pe(pe_comp, static=static)
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

    # data registers
    a = [comp.reg(bitwidth, f"a{i}") for i in range(n)]
    b = [comp.reg(bitwidth, f"b{i}") for i in range(n)]

    # indices to remember where to load from
    ia = [comp.reg(idx_size, f"ia{i}") for i in range(n)]
    ib = [comp.reg(idx_size, f"ib{i}") for i in range(n)]

    # decrementers
    subia = [comp.sub(idx_size, f"subia{i}") for i in range(n)]
    subib = [comp.sub(idx_size, f"subib{i}") for i in range(n)]

    # pes
    pe = [[comp.cell(f"pe_{i}_{j}", pe_comp) for j in range(n)] for i in range(n)]

    if static:
        group_1 = lambda x: comp.static_group(x, latency=1)
    else:
        group_1 = comp.group

    # routing within pes, and between pes and input
    with comp.continuous:
        for i in range(n):
            pe[i][0].ain = a[i].out
        for i in range(n):
            pe[0][i].bin = b[i].out
        for i in range(n):
            for j in range(1, n):
                pe[i][j].ain = pe[i][j - 1].aout
        for i in range(1, n):
            for j in range(n):
                pe[i][j].bin = pe[i - 1][j].bout

    # groups for loading from memory
    load_a = []
    for i in range(n):
        with group_1(f"load_a{i}") as g:
            mem.addr0 = cb.const(2, 0)
            mem.addr1 = cb.const(idx_size, i)
            mem.addr2 = ia[i].out
            a[i].in_ = mem.read_data
            a[i].write_en = cb.HI
            if not static:
                g.done = a[i].done
        load_a.append(g)

    load_b = []
    for i in range(n):
        with group_1(f"load_b{i}") as g:
            mem.addr0 = cb.const(2, 1)
            mem.addr1 = ib[i].out
            mem.addr2 = cb.const(idx_size, i)
            b[i].in_ = mem.read_data
            b[i].write_en = cb.HI
            if not static:
                g.done = b[i].done
        load_b.append(g)

    decr_a = []
    for i in range(n):
        with group_1(f"decr_ia{i}") as g:
            subia[i].left = ia[i].out
            subia[i].right = 1
            ia[i].in_ = subia[i].out
            ia[i].write_en = cb.HI
            if not static:
                g.done = ia[i].done
        decr_a.append(g)

    decr_b = []
    for i in range(n):
        with group_1(f"decr_ib{i}") as g:
            subib[i].left = ib[i].out
            subib[i].right = 1
            ib[i].in_ = subib[i].out
            ib[i].write_en = cb.HI
            if not static:
                g.done = ib[i].done
        decr_b.append(g)

    # groups for storing final results to memory
    store_pe = []
    for i in range(n):
        row = []
        for j in range(n):
            with group_1(f"store_pe_{i}_{j}") as g:
                mem.addr0 = cb.const(2, 2)
                mem.addr1 = cb.const(idx_size, i)
                mem.addr2 = cb.const(idx_size, j)
                mem.write_data = pe[i][j].out
                mem.write_en = cb.HI
                if not static:
                    g.done = mem.done
            row.append(g)
        store_pe.append(row)

    def reg_store(reg, val, groupname):
        with group_1(groupname) as g:
            reg.in_ = val
            reg.write_en = cb.HI
            if not static:
                g.done = reg.done
        return g

    # HACK!!!
    if static:
        old_par = cb.par
        old_invoke = cb.invoke
        old_SeqComp = ast.SeqComp
        cb.par = cb.static_par
        cb.invoke = cb.static_invoke
        ast.SeqComp = ast.StaticSeqComp

    control = [
        # initialization
        cb.par(
            *[reg_store(ia[i], n, f"init_ia{i}") for i in range(n)],
            *[reg_store(ib[i], n, f"init_ib{i}") for i in range(n)],
            *[cb.invoke(pe[i][j], in_clear=cb.HI) for i in range(n) for j in range(n)],
        )
    ]

    invoke_pes = cb.par(
        *[cb.invoke(pe[i][j], in_clear=cb.LO) for i in range(n) for j in range(n)]
    )
    clear_a = [reg_store(a[i], 0, f"clear_a{i}") for i in range(n)]
    clear_b = [reg_store(b[i], 0, f"clear_b{i}") for i in range(n)]

    # rounds of systolic action
    for r in range(1, n + 1):
        # a[0] through a[r-1] needs to be loaded with values
        # remaining registers should be cleared
        load_regs = [
            cb.par(
                *decr_a[:r],
                *decr_b[:r],
            ),
            *load_a[:r],
            *load_b[:r],
        ]
        # avoid an empty par section
        regs_to_clear = [*clear_a[r:n], *clear_b[r:n]]
        if regs_to_clear:
            control.extend([cb.par(load_regs, cb.par(*regs_to_clear)), invoke_pes])
        else:
            control.extend([*load_regs, invoke_pes])

    for r in range(n + 1, 2 * n):
        # a[r-n] through a[n-1] needs to be loaded with values
        # remaining registers should be cleared
        load_regs = [
            cb.par(
                *decr_a[r - n :],
                *decr_b[r - n :],
            ),
            *load_a[r - n :],
            *load_b[r - n :],
        ]
        clear_regs = cb.par(*clear_a[: r - n], *clear_b[: r - n])
        control.extend([cb.par(load_regs, clear_regs), invoke_pes])

    # now all data has been loaded, so clear registers to zero and churn
    control.append(cb.par(*clear_a, *clear_b))
    for r in range(2 * n, 3 * n - 1):
        control.append(invoke_pes)

    # store results
    control.extend([store_pe[i][j] for i in range(n) for j in range(n)])

    comp.control += control

    # end HACK
    if static:
        cb.par = old_par  # type: ignore
        cb.invoke = old_invoke  # type: ignore
        ast.SeqComp = old_SeqComp  # type: ignore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("size", help="size of the square matrix", default=2, type=int)
    parser.add_argument("--static", action="store_true")
    args = parser.parse_args()

    prog = cb.Builder(str(Path(__file__).resolve().parent))
    matmul_systolic_nxn(prog, args.size, static=args.static)
    prog.program.emit()


if __name__ == "__main__":
    sys.exit(main())
