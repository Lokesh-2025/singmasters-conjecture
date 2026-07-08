"""
phase3_grover.py
----------------
Phase 3: Tune the transpilation of Grover's search for 3003 in Pascal's Triangle.

The problem:
    Phase 2 used optimization_level=1 → 16,271 transpiled gates → noise floor.
    Jack Woehr's suggestion: tune the transpilation.

This script:
    1. Builds the SAME circuit as Phase 2 (4-qubit, find rows 14 & 15)
    2. Benchmarks all optimization levels + 5 qubit-mapping seeds — offline, free
    3. Picks the shortest result and submits to real hardware

Usage:
    python experiments/phase3_grover.py                    # benchmark only (free)
    python experiments/phase3_grover.py --submit           # submit best to hardware
    python experiments/phase3_grover.py --results JOB_ID  # retrieve results
    python experiments/phase3_grover.py --backend ibm_fez  # different machine
"""

import os, sys, math, argparse
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

# ── Same search target as Phase 2 ─────────────────────────────────────────────
N_QUBITS      = 4
MARKED_ROWS   = [14, 15]          # rows in Pascal's Triangle containing 3003
MARKED_STATES = ["1110", "1111"]  # binary representation of rows 14 and 15
N_MARKED      = len(MARKED_STATES)
SHOTS         = 2048              # more shots than Phase 2 for cleaner signal
BACKEND_NAME  = "ibm_marrakesh"

# Try 5 different qubit-mapping seeds — same circuit, different physical qubit layout
# The best layout can cut 2-qubit gate count significantly
SEEDS = [0, 42, 123, 456, 789]

# Optimal Grover iterations for 2 marked items in 16 total
N_ITERATIONS = max(1, math.floor(math.pi / 4 * math.sqrt((2**N_QUBITS) / N_MARKED)))


# ── Circuit (identical to Phase 2) ────────────────────────────────────────────

def build_oracle(qc):
    """Phase oracle: flip the phase of rows 14 and 15."""
    for state in MARKED_STATES:
        for i, bit in enumerate(reversed(state)):
            if bit == "0":
                qc.x(i)
        qc.h(N_QUBITS - 1)
        qc.mcx(list(range(N_QUBITS - 1)), N_QUBITS - 1)
        qc.h(N_QUBITS - 1)
        for i, bit in enumerate(reversed(state)):
            if bit == "0":
                qc.x(i)
        qc.barrier()


def build_diffusion(qc):
    """Grover diffusion operator (inversion about the mean)."""
    qc.h(range(N_QUBITS))
    qc.x(range(N_QUBITS))
    qc.h(N_QUBITS - 1)
    qc.mcx(list(range(N_QUBITS - 1)), N_QUBITS - 1)
    qc.h(N_QUBITS - 1)
    qc.x(range(N_QUBITS))
    qc.h(range(N_QUBITS))
    qc.barrier()


def build_circuit():
    qc = QuantumCircuit(N_QUBITS, N_QUBITS)
    qc.h(range(N_QUBITS))
    qc.barrier()
    for _ in range(N_ITERATIONS):
        build_oracle(qc)
        build_diffusion(qc)
    qc.measure(range(N_QUBITS), range(N_QUBITS))
    return qc


# ── Benchmark ─────────────────────────────────────────────────────────────────

def benchmark(backend):
    """
    Transpile the circuit with opt levels 1-3 and 5 seeds.
    No hardware used — this is pure classical simulation of the translation.
    Prints a table and returns the best (shortest) result.
    """
    qc = build_circuit()

    print(f"\n{'='*65}")
    print(f"Phase 3 Benchmark — Grover's Search for 3003")
    print(f"{'='*65}")
    print(f"Logical circuit:  depth={qc.depth()}, grover iters={N_ITERATIONS}")
    print(f"Phase 2 baseline: 16,271 transpiled gates (opt level 1, no seed)")
    print(f"Target:           < 2,000 gates for a clean signal")
    print(f"{'='*65}\n")

    print(f"{'Strategy':<32} {'Depth':>8}  {'2Q gates':>9}  {'Total gates':>11}")
    print(f"{'-'*65}")

    best_depth = float("inf")
    best = None

    for level in [1, 2, 3]:
        for seed in SEEDS:
            pm = generate_preset_pass_manager(
                backend=backend,
                optimization_level=level,
                seed_transpiler=seed,
            )
            isa = pm.run(qc)
            ops  = isa.count_ops()
            depth = isa.depth()
            # IBM machines use ECR as their native 2-qubit gate (not CX)
            two_q = ops.get("ecr", 0) + ops.get("cx", 0) + ops.get("cz", 0)
            total = sum(ops.values())
            label = f"opt={level}  seed={seed}"
            marker = " ← best" if depth < best_depth else ""
            print(f"  {label:<30} {depth:>8,}  {two_q:>9,}  {total:>11,}{marker}")

            if depth < best_depth:
                best_depth = depth
                best = (level, seed, isa, depth, two_q)

    level, seed, isa, depth, two_q = best
    reduction = round((1 - depth / 16271) * 100, 1)

    print(f"\n{'='*65}")
    print(f"Winner: opt={level}, seed={seed}")
    print(f"  Transpiled depth: {depth:,} gates")
    print(f"  2-qubit gates:    {two_q:,}")
    print(f"  Reduction from Phase 2: {reduction}%")
    print(f"{'='*65}")

    if depth <= 2000:
        print("✅ Below 2,000 — strong chance of signal on real hardware.")
    elif depth <= 5000:
        print("⚠️  Below 5,000 — might see weak signal. Worth submitting.")
    else:
        print("❌ Still too deep. Hardware likely won't show signal.")
        print("   Next step: rewrite the MCX gate decomposition manually.")

    return best


# ── Submit ────────────────────────────────────────────────────────────────────

def submit(backend):
    best = benchmark(backend)
    level, seed, isa, depth, two_q = best

    print(f"\nSubmitting best circuit to {backend.name}...")
    print(f"  opt={level}, seed={seed}, depth={depth:,}\n")

    sampler = Sampler(backend)
    job = sampler.run([isa], shots=SHOTS)
    job_id = job.job_id()

    print(f"Job submitted!  ID: {job_id}")
    print(f"\nTo get results:")
    print(f"  python experiments/phase3_grover.py --results {job_id}")


# ── Results ───────────────────────────────────────────────────────────────────

def get_results(job_id):
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform",
        token=os.getenv("IBM_QUANTUM_TOKEN"),
    )
    job    = service.job(job_id)
    result = job.result()

    bitarray = result[0].data
    field    = list(vars(bitarray).keys())[0]
    counts   = getattr(bitarray, field).get_counts()
    total    = sum(counts.values())

    print(f"\n{'='*60}")
    print(f"Phase 3 Results — Grover's Search for 3003 in Pascal's Triangle")
    print(f"{'='*60}\n")
    print("Top 8 measured states:")

    for state, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]:
        row = int(state, 2)
        pct = round(count / total * 100, 1)
        bar = "█" * int(pct / 2)
        found = " ← 3003 is here!" if row in MARKED_ROWS else ""
        print(f"  |{state}⟩ row {row:2d}: {count:4d} shots ({pct:5.1f}%) {bar}{found}")

    marked_total = sum(counts.get(s, 0) for s in MARKED_STATES)
    marked_pct   = round(marked_total / total * 100, 1)
    uniform_pct  = round(100 / (2**N_QUBITS) * N_MARKED, 1)
    amplification = round(marked_pct / uniform_pct, 2) if uniform_pct > 0 else 0

    print(f"\nMarked rows: {marked_total}/{total} shots = {marked_pct}%")
    print(f"Random baseline would give: {uniform_pct}%")
    print(f"Amplification: {amplification}×")

    print(f"\n── Experiment timeline ──────────────────────────────")
    print(f"  Phase 1  (  611 gates, opt=1):  4.11× ✅  signal clear")
    print(f"  Phase 2  (16,271 gates, opt=1):  1.04× ❌  noise floor")
    print(f"  Phase 3  (tuned):               {amplification}×  {'✅ signal!' if amplification > 1.5 else '⚠️ weak' if amplification > 1.1 else '❌ noise floor'}")

    if amplification > 1.5:
        print("\n✅ SUCCESS — transpilation tuning recovered the signal.")
        print("   The coherence window is wider than Phase 2's brute-force suggested.")
    elif amplification > 1.1:
        print("\n⚠️  PARTIAL — weak signal above noise. Try more shots or ibm_fez.")
    else:
        print("\n❌ Still noise floor. Next step: rewrite MCX to native CX chains.")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 3 — Grover transpilation tuning")
    parser.add_argument("--submit",  action="store_true", help="Submit best circuit to hardware")
    parser.add_argument("--results", metavar="JOB_ID",   help="Retrieve results for a job")
    parser.add_argument("--backend", default=BACKEND_NAME, help="IBM backend name")
    args = parser.parse_args()

    if args.results:
        get_results(args.results)
    else:
        token = os.getenv("IBM_QUANTUM_TOKEN")
        if not token:
            print("ERROR: IBM_QUANTUM_TOKEN not set in .env")
            sys.exit(1)
        service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token)
        backend = service.backend(args.backend)

        if args.submit:
            submit(backend)
        else:
            benchmark(backend)
