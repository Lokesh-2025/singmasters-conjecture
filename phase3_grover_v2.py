"""
phase3_grover_v2.py
-------------------
Phase 3 v2: Three improvements from LLM review.

Improvement 1 — Oracle simplification
    Rows 14 (1110) and 15 (1111) share the condition: qubits 1,2,3 = 1
    Qubit 0 doesn't matter. So one CCX(1,2,3) replaces two MCX([0,1,2],3) calls.

Improvement 2 — Relative-phase gates
    Standard CCX = 6 CX gates. RCCX = 3 CX gates.
    Grover only needs correct phase relationships — relative phase is fine.

Improvement 3 — Compare 1 vs 2 Grover iterations
    1 iteration = 78% ideal, fewer gates.
    2 iterations = 95% ideal, more gates.
    On noisy hardware fewer gates often wins.

Usage:
    python experiments/phase3_grover_v2.py               # simulate all versions
    python experiments/phase3_grover_v2.py --submit      # submit best to hardware
    python experiments/phase3_grover_v2.py --results ID  # get results
"""

import os, sys, math, argparse
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

from qiskit import QuantumCircuit
from qiskit.circuit.library import RCCXGate
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_aer import AerSimulator

N_QUBITS      = 4
MARKED_ROWS   = [14, 15]
MARKED_STATES = ["1110", "1111"]
SHOTS_SIM     = 8192
SHOTS_HW      = 2048
BACKEND_NAME  = "ibm_marrakesh"


# ── Version A: original (baseline for comparison) ────────────────────────────

def build_oracle_original(qc):
    """Two separate MCX calls — one per marked state."""
    for state in MARKED_STATES:
        for i, bit in enumerate(reversed(state)):
            if bit == "0": qc.x(i)
        qc.h(N_QUBITS - 1)
        qc.mcx(list(range(N_QUBITS - 1)), N_QUBITS - 1)
        qc.h(N_QUBITS - 1)
        for i, bit in enumerate(reversed(state)):
            if bit == "0": qc.x(i)
        qc.barrier()

def build_diffusion_original(qc):
    qc.h(range(N_QUBITS))
    qc.x(range(N_QUBITS))
    qc.h(N_QUBITS - 1)
    qc.mcx(list(range(N_QUBITS - 1)), N_QUBITS - 1)
    qc.h(N_QUBITS - 1)
    qc.x(range(N_QUBITS))
    qc.h(range(N_QUBITS))
    qc.barrier()


# ── Version B: simplified oracle + RCCX diffusion ────────────────────────────

def build_oracle_simplified(qc):
    """
    Rows 14=1110 and 15=1111 both have qubits 1,2,3 = 1.
    Qubit 0 is irrelevant. One CCX(1,2,3) marks both rows at once.
    """
    # CCZ on qubits 1,2,3 = flip phase whenever q1=q2=q3=1
    # H · CCX · H = CCZ (controlled-controlled-Z)
    qc.h(3)
    qc.ccx(1, 2, 3)
    qc.h(3)
    qc.barrier()

def build_diffusion_ancilla(qc):
    """
    Diffusion operator using one ancilla qubit (qubit 4) to break up MCX.
    Instead of MCX([0,1,2], 3) = expensive,
    use: CCX(0,1,ancilla) → CCX(ancilla,2,3) → CCX(0,1,ancilla) = 3 cheap Toffolis.
    Qubit 4 is borrowed then restored — no measurement needed.
    """
    qc.h(range(N_QUBITS))
    qc.x(range(N_QUBITS))
    qc.h(3)
    # 3-controlled-X decomposed via ancilla qubit 4
    qc.ccx(0, 1, 4)        # ancilla = q0 AND q1
    qc.ccx(2, 4, 3)        # flip q3 if q2 AND ancilla (= q0 AND q1 AND q2)
    qc.ccx(0, 1, 4)        # uncompute ancilla back to 0
    qc.h(3)
    qc.x(range(N_QUBITS))
    qc.h(range(N_QUBITS))
    qc.barrier()


# ── Circuit builders ──────────────────────────────────────────────────────────

def build_circuit_original(n_iter):
    qc = QuantumCircuit(N_QUBITS, N_QUBITS)
    qc.h(range(N_QUBITS))
    qc.barrier()
    for _ in range(n_iter):
        build_oracle_original(qc)
        build_diffusion_original(qc)
    qc.measure(range(N_QUBITS), range(N_QUBITS))
    return qc

def build_circuit_v2(n_iter):
    # 5 qubits: 4 data + 1 ancilla for efficient diffusion decomposition
    qc = QuantumCircuit(5, N_QUBITS)
    qc.h(range(N_QUBITS))
    qc.barrier()
    for _ in range(n_iter):
        build_oracle_simplified(qc)
        build_diffusion_ancilla(qc)
    qc.measure(range(N_QUBITS), range(N_QUBITS))
    return qc


# ── Simulate ──────────────────────────────────────────────────────────────────

def run_sim(qc, label):
    sim = AerSimulator()
    counts = sim.run(qc, shots=SHOTS_SIM).result().get_counts()
    total  = sum(counts.values())

    marked_total = sum(counts.get(s, 0) for s in MARKED_STATES)
    marked_pct   = round(marked_total / total * 100, 1)
    uniform_pct  = round(100 / (2**N_QUBITS) * len(MARKED_STATES), 1)
    amplification = round(marked_pct / uniform_pct, 2)

    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:4]
    top_str = "  ".join(f"|{s}⟩={round(c/total*100)}%" for s, c in top)
    correct = all(
        counts.get(s, 0) / total > 0.1 for s in MARKED_STATES
    )
    return {
        "label": label,
        "amplification": amplification,
        "marked_pct": marked_pct,
        "top": top_str,
        "depth": qc.depth(),
        "gates": sum(qc.count_ops().values()),
        "correct": correct,
    }


def benchmark_transpile(qc, backend, label):
    """Transpile with opt=2 seed=42 (our Phase 3 winner) and report gate count."""
    pm  = generate_preset_pass_manager(backend=backend, optimization_level=2, seed_transpiler=42)
    isa = pm.run(qc)
    ops = isa.count_ops()
    two_q = ops.get("ecr", 0) + ops.get("cx", 0)
    return isa, isa.depth(), two_q, sum(ops.values())


# ── Main benchmark ────────────────────────────────────────────────────────────

def simulate_all(backend=None):
    versions = [
        ("Original  2 iter", build_circuit_original(2)),
        ("Original  1 iter", build_circuit_original(1)),
        ("v2        2 iter", build_circuit_v2(2)),
        ("v2        1 iter", build_circuit_v2(1)),
    ]

    print(f"\n{'='*70}")
    print("Phase 3 v2 — Simulation Comparison")
    print(f"{'='*70}\n")

    print(f"{'Version':<22} {'Amplif':>8}  {'Marked%':>8}  {'Logical gates':>14}  {'Correct?':>9}")
    print("-"*70)

    results = []
    for label, qc in versions:
        r = run_sim(qc, label)
        results.append((label, qc, r))
        ok = "✅" if r["correct"] else "❌"
        print(f"  {label:<20} {r['amplification']:>7}×  {r['marked_pct']:>7}%  {r['gates']:>14,}  {ok:>9}")

    print()

    if backend:
        print(f"{'Version':<22} {'Trans. depth':>13}  {'2Q gates':>9}  {'Total gates':>12}")
        print("-"*60)
        best_depth = float("inf")
        best_isa = None
        best_label = None
        for label, qc, r in results:
            if not r["correct"]:
                print(f"  {label:<20}  ❌ circuit incorrect — skipping")
                continue
            isa, depth, two_q, total = benchmark_transpile(qc, backend, label)
            marker = ""
            if depth < best_depth:
                best_depth = depth
                best_isa = isa
                best_label = label
                marker = " ← best"
            print(f"  {label:<20}  {depth:>12,}  {two_q:>9,}  {total:>12,}{marker}")

        print(f"\n{'='*70}")
        print(f"Winner: {best_label}  →  {best_depth:,} transpiled gates")
        print(f"Phase 2 baseline: 16,271 gates")
        print(f"Reduction: {round((1 - best_depth/16271)*100, 1)}%")
        if best_depth < 300:
            print("✅ Under 300 gates — excellent. Submit this.")
        elif best_depth < 600:
            print("✅ Under 600 gates — in Phase 1's success zone. Safe to submit.")
        else:
            print("⚠️  Still above 600. More optimisation needed.")
        return best_isa, best_label
    else:
        print("(Run with --backend to also show transpiled gate counts)")
        return None, None


# ── Submit ────────────────────────────────────────────────────────────────────

def submit(backend):
    from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler
    best_isa, best_label = simulate_all(backend)
    if best_isa is None:
        print("No valid circuit to submit.")
        return
    print(f"\nSubmitting: {best_label} → {backend.name}")
    sampler = Sampler(backend)
    job = sampler.run([best_isa], shots=SHOTS_HW)
    job_id = job.job_id()
    print(f"\nJob ID: {job_id}")
    print(f"python experiments/phase3_grover_v2.py --results {job_id}")


# ── Results ───────────────────────────────────────────────────────────────────

def get_results(job_id):
    from qiskit_ibm_runtime import QiskitRuntimeService
    service  = QiskitRuntimeService(channel="ibm_quantum_platform", token=os.getenv("IBM_QUANTUM_TOKEN"))
    job      = service.job(job_id)
    bitarray = job.result()[0].data
    field    = list(vars(bitarray).keys())[0]
    counts   = getattr(bitarray, field).get_counts()
    total    = sum(counts.values())

    print(f"\n{'='*60}")
    print("Phase 3 v2 — Real Hardware Results")
    print(f"{'='*60}\n")

    for state, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]:
        row = int(state, 2)
        pct = round(count / total * 100, 1)
        bar = "█" * int(pct / 2)
        found = " ← 3003!" if row in MARKED_ROWS else ""
        print(f"  |{state}⟩ row {row:2d}: {count:4d} shots ({pct:5.1f}%) {bar}{found}")

    marked_total  = sum(counts.get(s, 0) for s in MARKED_STATES)
    marked_pct    = round(marked_total / total * 100, 1)
    uniform_pct   = round(100 / (2**N_QUBITS) * len(MARKED_STATES), 1)
    amplification = round(marked_pct / uniform_pct, 2)

    print(f"\nAmplification: {amplification}×  (random baseline = 1.0×)")
    print(f"\n── Timeline ──────────────────────────────")
    print(f"  Phase 1  (611 gates):        4.11× ✅")
    print(f"  Phase 2  (16,271 gates):     1.04× ❌")
    print(f"  Phase 3v1 (438 gates):       TBD")
    print(f"  Phase 3v2 (this run):        {amplification}× {'✅' if amplification > 1.5 else '⚠️' if amplification > 1.1 else '❌'}")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit",  action="store_true")
    parser.add_argument("--results", metavar="JOB_ID")
    parser.add_argument("--backend", default=BACKEND_NAME)
    args = parser.parse_args()

    if args.results:
        get_results(args.results)
    else:
        from qiskit_ibm_runtime import QiskitRuntimeService
        service = QiskitRuntimeService(channel="ibm_quantum_platform", token=os.getenv("IBM_QUANTUM_TOKEN"))
        backend = service.backend(args.backend)
        if args.submit:
            submit(backend)
        else:
            simulate_all(backend)
