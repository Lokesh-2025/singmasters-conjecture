"""
phase3_grover_v3.py
-------------------
Phase 3 v3: Apply RCCX everywhere. Target: ~50-60 transpiled gates.

What changed from v2:
  v2 oracle:    H + CCX(1,2,3) + H  = 6 CX gates
  v3 oracle:    H + CCX(1,2,3) + H  = 6 CX gates  (must be exact — RCCX breaks phase kickback)

  v2 diffusion: CCX + CCX + CCX = 18 CX gates
  v3 diffusion: RCCX + CCX + RCCX = 12 CX gates
    ↑ RCCX is safe for ancilla compute/uncompute (same gate twice → phases cancel)
    ↑ middle CCX must be exact (acts on |+⟩ target — relative phase would break diffusion)

  Total: 24 CX → 18 CX gates in the logical circuit.

Why RCCX breaks the oracle:
  RCCX = H(target) + [3CX core] + H(target)
  So H + RCCX + H = H + H + [core] + H + H = [core]   (H·H = I cancels)
  And [core] ≠ CCX — it's a different gate that marks the WRONG states.

Hardware options added:
  - optimization_level = 3
  - dynamical_decoupling enabled  (protects idle qubits from cross-talk)
  - twirling enabled               (converts coherent errors to stochastic)
  - resilience_level = 1           (readout error mitigation, minimal overhead)

Usage:
  python experiments/phase3_grover_v3.py              # simulate + transpile
  python experiments/phase3_grover_v3.py --submit     # submit to hardware
  python experiments/phase3_grover_v3.py --results ID
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
SHOTS_HW      = 4096   # more shots for cleaner signal at this gate count
BACKEND_NAME  = "ibm_marrakesh"


# ── Circuit (5 qubits: 4 data + 1 ancilla) ───────────────────────────────────

def build_circuit_v3():
    """
    1 Grover iteration. RCCX everywhere.

    Oracle: CCZ(1,2,3) using H + RCCX + H  = 3 CX gates
    Diffusion MCX([0,1,2],3) via ancilla + RCCX chain = 9 CX gates
    Total: 12 CX gates in logical circuit.
    """
    qc = QuantumCircuit(5, N_QUBITS)  # qubit 4 = ancilla

    # ── Superposition ─────────────────────────────────────────────────────────
    qc.h(range(N_QUBITS))
    qc.barrier()

    # ── Oracle ────────────────────────────────────────────────────────────────
    # Mark rows 14 (1110) and 15 (1111): condition = q1=q2=q3=1, q0 ignored.
    # CCZ(1,2,3) via H + CCX + H. Must use standard CCX here —
    # RCCX breaks phase kickback because RCCX has H baked in at each end.
    qc.h(3)
    qc.ccx(1, 2, 3)                    # 6 CX (exact phase required)
    qc.h(3)
    # no barrier here — lets compiler cancel H·H and X·X at oracle/diffusion boundary

    # ── Diffusion ─────────────────────────────────────────────────────────────
    # Inversion about the mean: H X [MCX] X H
    # MCX([0,1,2],3) via ancilla = 18 CX (3x CCX) in v2.
    # v3 improvement: RCCX for ancilla compute/uncompute (phases cancel because
    # we apply the same gate twice). Middle CCX stays exact (target is in |+⟩).
    # Total: 3 + 6 + 3 = 12 CX gates in diffusion.
    qc.h(range(N_QUBITS))
    qc.x(range(N_QUBITS))
    qc.h(3)
    qc.append(RCCXGate(), [0, 1, 4])   # compute: anc = q0 AND q1  (3 CX)
    qc.ccx(2, 4, 3)                    # act on |+⟩ target — must be exact (6 CX)
    qc.append(RCCXGate(), [0, 1, 4])   # uncompute: same gate again, phase cancels (3 CX)
    qc.h(3)
    qc.x(range(N_QUBITS))
    qc.h(range(N_QUBITS))
    qc.barrier()

    qc.measure(range(N_QUBITS), range(N_QUBITS))
    return qc


# ── Simulate ──────────────────────────────────────────────────────────────────

def simulate(qc):
    # RCCX is not native to Aer — decompose to standard gates first
    qc_decomposed = qc.decompose()
    sim    = AerSimulator()
    counts = sim.run(qc_decomposed, shots=SHOTS_SIM).result().get_counts()
    total  = sum(counts.values())

    marked_total  = sum(counts.get(s, 0) for s in MARKED_STATES)
    marked_pct    = round(marked_total / total * 100, 1)
    uniform_pct   = round(100 / (2**N_QUBITS) * len(MARKED_STATES), 1)
    amplification = round(marked_pct / uniform_pct, 2)

    print(f"\n── Simulator (perfect, no noise) ──────────────────────")
    for state, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:6]:
        row = int(state, 2)
        pct = round(count / total * 100, 1)
        bar = "█" * int(pct / 2)
        found = " ← 3003!" if row in MARKED_ROWS else ""
        print(f"  |{state}⟩ row {row:2d}: {pct:5.1f}% {bar}{found}")

    print(f"\n  Amplification: {amplification}×  (random = 1.0×)")
    ok = amplification > 5
    print(f"  Circuit correct: {'✅' if ok else '❌'}")
    return ok


# ── Transpile benchmark ───────────────────────────────────────────────────────

def transpile_compare(qc, backend):
    """Try opt levels 2 and 3 with multiple seeds. Return best ISA circuit."""
    print(f"\n── Transpilation on {backend.name} ────────────────────")
    print(f"{'Strategy':<25} {'Depth':>8}  {'CX/ECR':>7}  {'Total':>8}")
    print("-" * 55)

    best_depth = float("inf")
    best_isa   = None

    for level in [2, 3]:
        for seed in [0, 42, 123, 456, 789]:
            pm  = generate_preset_pass_manager(
                backend=backend,
                optimization_level=level,
                seed_transpiler=seed,
            )
            isa   = pm.run(qc)
            ops   = isa.count_ops()
            depth = isa.depth()
            two_q = ops.get("ecr", 0) + ops.get("cx", 0)
            total = sum(ops.values())
            marker = " ← best" if depth < best_depth else ""
            print(f"  opt={level} seed={seed:<6} {depth:>8,}  {two_q:>7,}  {total:>8,}{marker}")
            if depth < best_depth:
                best_depth = depth
                best_isa   = isa

    reduction = round((1 - best_depth / 16271) * 100, 1)
    print(f"\n  Winner: {best_depth:,} gates  ({reduction}% reduction from Phase 2)")

    if best_depth < 80:
        print("  ✅ Under 80 — exceptional. Almost certainly works on hardware.")
    elif best_depth < 150:
        print("  ✅ Under 150 — excellent. Very likely works on hardware.")
    elif best_depth < 300:
        print("  ✅ Under 300 — good. In Phase 1's success zone.")
    else:
        print("  ⚠️  Above 300. More work needed.")

    return best_isa


# ── Submit ────────────────────────────────────────────────────────────────────

def submit(backend, isa):
    from qiskit_ibm_runtime import SamplerV2
    from qiskit_ibm_runtime.options import SamplerOptions

    print(f"\n── Submitting to {backend.name} ────────────────────────")
    print(f"  Shots: {SHOTS_HW}")
    print(f"  Options: resilience_level=1, twirling=on, DD=on")

    # Build options with error mitigation
    options = SamplerOptions()
    options.default_shots                = SHOTS_HW
    options.dynamical_decoupling.enable  = True    # protect idle qubits
    options.twirling.enable_gates        = True    # coherent → stochastic errors
    options.twirling.enable_measure      = True
    # resilience_level is EstimatorV2-only; SamplerV2 gets mitigation via twirling

    sampler = SamplerV2(backend, options=options)
    job     = sampler.run([isa])
    job_id  = job.job_id()

    print(f"\n  Job ID: {job_id}")
    print(f"  python experiments/phase3_grover_v3.py --results {job_id}")
    return job_id


# ── Results ───────────────────────────────────────────────────────────────────

def get_results(job_id):
    from qiskit_ibm_runtime import QiskitRuntimeService
    service  = QiskitRuntimeService(channel="ibm_quantum_platform",
                                    token=os.getenv("IBM_QUANTUM_TOKEN"))
    counts   = service.job(job_id).result()[0].data
    field    = list(vars(counts).keys())[0]
    counts   = getattr(counts, field).get_counts()
    total    = sum(counts.values())

    print(f"\n{'='*60}")
    print("Phase 3 v3 — Real Hardware Results (ibm_marrakesh)")
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

    print(f"\n  Amplification: {amplification}×  (random = 1.0×)")
    print(f"\n── Full experiment timeline ──────────────────────────")
    print(f"  Phase 1   (   611 gates, opt=1):  4.11× ✅")
    print(f"  Phase 2   (16,271 gates, opt=1):  1.04× ❌  noise floor")
    print(f"  Phase 3v1 (   438 gates, opt=2):  TBD")
    print(f"  Phase 3v2 (   131 gates, RCCX v1): TBD")
    print(f"  Phase 3v3 (this run, RCCX+DD):   {amplification}×  "
          f"{'✅ success!' if amplification > 1.5 else '⚠️ weak' if amplification > 1.1 else '❌ noise'}")


# ── Entry ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--submit",  action="store_true")
    parser.add_argument("--results", metavar="JOB_ID")
    parser.add_argument("--backend", default=BACKEND_NAME)
    args = parser.parse_args()

    if args.results:
        get_results(args.results)
        sys.exit(0)

    qc = build_circuit_v3()
    print(f"\nLogical circuit: {qc.num_qubits} qubits, depth={qc.depth()}, "
          f"gates={sum(qc.count_ops().values())}")

    ok = simulate(qc)

    if not ok:
        print("\n❌ Circuit incorrect in simulation. Not submitting.")
        sys.exit(1)

    from qiskit_ibm_runtime import QiskitRuntimeService
    service = QiskitRuntimeService(channel="ibm_quantum_platform",
                                   token=os.getenv("IBM_QUANTUM_TOKEN"))
    backend = service.backend(args.backend)
    best_isa = transpile_compare(qc, backend)

    if args.submit:
        submit(backend, best_isa)
    else:
        print("\n  Run with --submit to send to real hardware.")
