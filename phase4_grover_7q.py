"""
phase4_grover_7q.py
-------------------
Phase 4: 7-qubit Grover search for 3003 in rows 0-127 of Pascal's Triangle.

Marked states: rows 14, 15, 78
  Row 14 = 0001110  →  C(14,6) = 3003
  Row 15 = 0001111  →  C(15,5) = 3003
  Row 78 = 1001110  →  C(78,2) = 3003

ALL optimisation techniques applied:

ORACLE — shared Boolean factoring
  Shared condition: q3=q2=q1=1 AND q4=0 AND q5=0  (all 3 rows have this)
  Term A: a3=1 AND q6=0           → marks rows 14 and 15 (one CCX kickback)
  Term B: a3=1 AND q6=1 AND q0=0  → marks row 78           (CCX via temp ancilla)

DIFFUSION — ancilla chain
  RCCX for compute/uncompute (same gate twice → relative phases cancel)
  CCX for the phase-kickback step on Q6 (exact phase needed)

HARDWARE
  4 Grover iterations (optimal for M=3, N=128)
  50-seed sweep to find lowest-depth transpilation
  Dynamical decoupling + Pauli twirling

Usage:
  python3 experiments/phase4_grover_7q.py              # 3-stage simulation
  python3 experiments/phase4_grover_7q.py --transpile  # transpile + count gates
  python3 experiments/phase4_grover_7q.py --smoke      # 1-iter hardware test
  python3 experiments/phase4_grover_7q.py --submit     # full 4-iter hardware run
  python3 experiments/phase4_grover_7q.py --results ID
"""

import os, sys, argparse
from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

from qiskit import QuantumCircuit
from qiskit.circuit.library import RCCXGate
from qiskit.quantum_info import Statevector
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_aer import AerSimulator

# ── Constants ─────────────────────────────────────────────────────────────────

N_DATA      = 7
N_ANC       = 4            # A0,A1,A2,A3 (compute chain — A3 doubles as phase target)
N_TOTAL     = N_DATA + N_ANC   # 11 qubits
MARKED_ROWS = [14, 15, 78]
MARKED_BITS = ["0001110", "0001111", "1001110"]   # q6q5q4q3q2q1q0 (MSB first)
N_SEARCH    = 128
SHOTS_SMOKE = 1024
SHOTS_FULL  = 4096
BACKEND_NAME = "ibm_marrakesh"

# Qubit aliases
Q0,Q1,Q2,Q3,Q4,Q5,Q6 = range(7)
D = list(range(7))          # data qubit list
A0,A1,A2,A3 = 7,8,9,10


# ── Oracle ────────────────────────────────────────────────────────────────────

def build_oracle(qc):
    """
    Phase oracle marking rows 14, 15, 78.

    KEY INSIGHT — use A3 as the phase kickback target (same trick as Phase 3 v3 used Q3):
      H(A3=|1>) = |-> ,  then CX/CCX flips -> phase -1,  then H restores A3 to |1>.
      H(A3=|0>) = |+> ,  CX|+> = |+> (no kickback),      H restores A3 to |0>.
    So phase -1 is applied ONLY when A3=1 AND the CX/CCX control fires.

    Shared condition (A3=1): q3=q2=q1=1 AND q4=0 AND q5=0  (common to all 3 rows)

    Term A  — H(A3)·CX(Q6_inv, A3)·H(A3) = CZ(Q6_inv, A3)
      Adds phase -1 when A3=1 AND q6=0  →  marks rows 14, 15

    Term B  — H(A3)·CCX(Q6, Q0_inv, A3)·H(A3) = CCZ(Q6, Q0_inv, A3)
      Adds phase -1 when A3=1 AND q6=1 AND q0=0  →  marks row 78 only
      Does NOT re-mark row 79 (q6=1, q0=1) because Q0_inv=0 after X(Q0).
    """
    # Flip bits that should be 0 in the shared condition
    qc.x(Q4)
    qc.x(Q5)

    # Compute shared condition → A3
    # RCCX safe here: same gate used for uncompute (relative phases cancel)
    qc.append(RCCXGate(), [Q1, Q2, A0])   # A0 = q1 AND q2
    qc.append(RCCXGate(), [A0, Q3, A1])   # A1 = ... AND q3
    qc.append(RCCXGate(), [A1, Q4, A2])   # A2 = ... AND NOT(q4_orig)  [q4 is now flipped]
    qc.ccx(A2, Q5, A3)                     # A3 = full shared  (exact CCX)

    # Term A: CZ(Q6_inv, A3)  →  phase -1 when A3=1 AND q6=0
    qc.x(Q6)                               # flip so Q6=1 means original q6=0
    qc.h(A3)
    qc.cx(Q6, A3)                          # CX: A3 is |-> → phase -1 when Q6=1
    qc.h(A3)
    qc.x(Q6)                               # restore

    # Term B: CCZ(Q6, Q0_inv, A3)  →  phase -1 when A3=1 AND q6=1 AND q0=0
    qc.x(Q0)                               # flip so Q0=1 means original q0=0
    qc.h(A3)
    qc.ccx(Q6, Q0, A3)                    # CCX: A3 is |-> → phase -1 when Q6=1 AND Q0=1
    qc.h(A3)
    qc.x(Q0)                               # restore

    # Uncompute shared condition (EXACT reverse order)
    qc.ccx(A2, Q5, A3)
    qc.append(RCCXGate(), [A1, Q4, A2])
    qc.append(RCCXGate(), [A0, Q3, A1])
    qc.append(RCCXGate(), [Q1, Q2, A0])

    # Restore flipped bits
    qc.x(Q5)
    qc.x(Q4)


# ── Diffusion ─────────────────────────────────────────────────────────────────

def build_diffusion(qc):
    """
    7-qubit Grover diffusion (inversion about the mean).

    Implements: H(D)·X(D)·MCZ(D)·X(D)·H(D)
    where MCZ(D) = H(Q6)·MCX([Q0..Q5],Q6)·H(Q6)

    MCX chain: RCCX for ancilla compute/uncompute, CCX for final phase step.
    Same pattern as Phase 3 v3 diffusion (proven correct on hardware).
    """
    qc.h(D)
    qc.x(D)
    qc.h(Q6)   # extra H on target: H·X·H puts Q6 in kickback basis

    # Compute chain: A0=Q0∧Q1, A1=...∧Q2, A2=...∧Q3, A3=...∧Q4
    qc.append(RCCXGate(), [Q0, Q1, A0])
    qc.append(RCCXGate(), [A0, Q2, A1])
    qc.append(RCCXGate(), [A1, Q3, A2])
    qc.append(RCCXGate(), [A2, Q4, A3])
    qc.ccx(A3, Q5, Q6)   # exact CCX on Q6 (superposition target)

    # Uncompute (reverse order)
    qc.append(RCCXGate(), [A2, Q4, A3])
    qc.append(RCCXGate(), [A1, Q3, A2])
    qc.append(RCCXGate(), [A0, Q2, A1])
    qc.append(RCCXGate(), [Q0, Q1, A0])

    qc.h(Q6)
    qc.x(D)
    qc.h(D)
    qc.barrier()


# ── Full circuit ──────────────────────────────────────────────────────────────

def build_circuit(n_iter=4):
    qc = QuantumCircuit(N_TOTAL, N_DATA)
    qc.h(D)
    qc.barrier()
    for _ in range(n_iter):
        build_oracle(qc)
        build_diffusion(qc)
    qc.measure(D, range(N_DATA))
    return qc


# ── Stage A: Oracle unit test ─────────────────────────────────────────────────

def verify_oracle():
    """Apply oracle to each basis state. Only rows 14, 15, 78 should get phase -1."""
    print("\n── Stage A: Oracle Phase Verification ──────────────────")
    errors = 0
    for row in range(N_SEARCH):
        bits = format(row, f'0{N_DATA}b')   # MSB first
        qc_test = QuantumCircuit(N_TOTAL)
        # Set data qubits — reversed(bits) gives LSB=q0 first
        for i, bit in enumerate(reversed(bits)):
            if bit == '1':
                qc_test.x(D[i])
        build_oracle(qc_test)
        sv  = Statevector(qc_test)
        amp = sv[row]   # ancilla all 0, so data-only index = row
        phase = (amp / abs(amp)).real if abs(amp) > 1e-9 else 1.0

        should_flip = row in MARKED_ROWS
        did_flip    = phase < -0.5

        if should_flip != did_flip:
            errors += 1
            tag = "❌ WRONG"
        elif should_flip:
            tag = "✅ marked"
        else:
            tag = "✓"

        if should_flip or did_flip:
            print(f"  Row {row:3d} ({bits}): phase={phase:+.3f}  {tag}")

    if errors == 0:
        print(f"\n  ✅ Oracle correct — only rows {MARKED_ROWS} phase-flipped.")
        return True
    print(f"\n  ❌ {errors} oracle errors. Fix before continuing.")
    return False


# ── Stage B: 1-iteration simulation ───────────────────────────────────────────

def simulate(qc, shots=8192):
    """Decompose RCCX to CX basis before running on Aer."""
    from qiskit import transpile
    qc_dec = transpile(qc, basis_gates=["cx", "u", "x", "h", "z", "s", "t", "measure"])
    return AerSimulator().run(qc_dec, shots=shots).result().get_counts()


def verify_one_iter():
    """1 Grover iteration. Marked states should rise from 0.78% to ~6-10%."""
    print("\n── Stage B: 1-Iteration Simulation ────────────────────")
    qc     = build_circuit(n_iter=1)
    counts = simulate(qc)
    total  = sum(counts.values())

    marked_total  = sum(counts.get(b, 0) for b in MARKED_BITS)
    marked_pct    = round(marked_total / total * 100, 1)
    random_pct    = round(100 / N_SEARCH * len(MARKED_ROWS), 1)
    amplification = round(marked_pct / random_pct, 2) if random_pct else 0

    print(f"  Random baseline: {random_pct}%  |  Got: {marked_pct}%  |  {amplification}×\n")
    for bits in MARKED_BITS:
        row   = int(bits, 2)
        count = counts.get(bits, 0)
        print(f"  Row {row:3d} ({bits}): {round(count/total*100,1)}%")

    if amplification > 1.5:
        print(f"\n  ✅ Signal confirmed after 1 iteration.")
        return True
    print(f"\n  ❌ Weak signal. Check oracle and diffusion.")
    return False


# ── Stage C: Full 4-iteration simulation ──────────────────────────────────────

def verify_full():
    """4 Grover iterations. Marked states should capture >80% combined."""
    print("\n── Stage C: Full 4-Iteration Simulation ───────────────")
    qc     = build_circuit(n_iter=4)
    counts = simulate(qc)
    total  = sum(counts.values())

    top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for bits, count in top:
        row = int(bits, 2)
        pct = round(count / total * 100, 1)
        bar = "█" * int(pct)
        tag = " ← 3003!" if row in MARKED_ROWS else ""
        print(f"  Row {row:3d} ({bits}): {pct:5.1f}% {bar}{tag}")

    marked_total  = sum(counts.get(b, 0) for b in MARKED_BITS)
    marked_pct    = round(marked_total / total * 100, 1)
    random_pct    = round(100 / N_SEARCH * len(MARKED_ROWS), 1)
    amplification = round(marked_pct / random_pct, 2) if random_pct else 0

    print(f"\n  Amplification: {amplification}×")
    if marked_pct > 80:
        print(f"  ✅ {marked_pct}% on marked states — ready for hardware.")
        return True
    elif marked_pct > 50:
        print(f"  ⚠️  {marked_pct}% — acceptable, but consider optimising iterations.")
        return True
    print(f"  ❌ Only {marked_pct}% — do not submit to hardware.")
    return False


# ── Transpile ─────────────────────────────────────────────────────────────────

def transpile_check(backend, n_iter=4):
    """50-seed sweep at opt levels 2 and 3. Returns best ISA circuit."""
    print(f"\n── Transpilation  backend={backend.name}  n_iter={n_iter} ──")
    qc = build_circuit(n_iter=n_iter)
    best_total, best_isa = float("inf"), None

    print(f"  {'opt':>4}  {'seed':>5}  {'depth':>7}  {'CZ':>5}  {'total':>7}")
    print(f"  {'-'*38}")
    for level in [2, 3]:
        for seed in range(50):
            pm  = generate_preset_pass_manager(
                backend=backend, optimization_level=level, seed_transpiler=seed)
            isa   = pm.run(qc)
            ops   = isa.count_ops()
            depth = isa.depth()
            cz    = ops.get("cz", 0) + ops.get("ecr", 0) + ops.get("cx", 0)
            total = sum(ops.values())
            tag   = " ← best" if total < best_total else ""
            if total < best_total or seed % 10 == 0:
                print(f"  {level:>4}  {seed:>5}  {depth:>7,}  {cz:>5,}  {total:>7,}{tag}")
            if total < best_total:
                best_total, best_isa = total, isa

    print(f"\n  Best: {best_total} total gates")
    if best_total < 350:
        print(f"  ✅ Under 350 — submit confidently.")
    elif best_total < 450:
        print(f"  ⚠️  Under 450 — submit with caution.")
    else:
        print(f"  ❌ Over 450 — optimise before spending QPU credits.")
    return best_isa, best_total


# ── Submit ────────────────────────────────────────────────────────────────────

def submit_job(backend, isa, shots, label):
    from qiskit_ibm_runtime import SamplerV2
    from qiskit_ibm_runtime.options import SamplerOptions

    print(f"\n── Submitting: {label}  ({shots} shots)")
    options = SamplerOptions()
    options.default_shots               = shots
    options.dynamical_decoupling.enable = True
    options.twirling.enable_gates       = True
    options.twirling.enable_measure     = True

    job    = SamplerV2(backend, options=options).run([isa])
    job_id = job.job_id()
    print(f"  Job ID: {job_id}")
    print(f"  python3 experiments/phase4_grover_7q.py --results {job_id}")
    return job_id


# ── Results ───────────────────────────────────────────────────────────────────

def get_results(job_id):
    from qiskit_ibm_runtime import QiskitRuntimeService
    service = QiskitRuntimeService(channel="ibm_quantum_platform",
                                   token=os.getenv("IBM_QUANTUM_TOKEN"))
    result = service.job(job_id).result()[0].data
    field  = list(vars(result).keys())[0]
    counts = getattr(result, field).get_counts()
    total  = sum(counts.values())

    print(f"\n{'='*62}")
    print("Phase 4  —  7-Qubit Grover  (ibm_marrakesh)")
    print(f"{'='*62}\n")
    for bits, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        row = int(bits, 2)
        pct = round(count / total * 100, 1)
        tag = " ← 3003!" if row in MARKED_ROWS else ""
        print(f"  Row {row:3d} ({bits}): {count:4d} shots  ({pct:5.1f}%) {'█'*int(pct/2)}{tag}")

    marked_pct    = round(sum(counts.get(b, 0) for b in MARKED_BITS) / total * 100, 1)
    random_pct    = round(100 / N_SEARCH * len(MARKED_ROWS), 1)
    amplification = round(marked_pct / random_pct, 2) if random_pct else 0
    print(f"\n  Amplification: {amplification}×")
    print(f"\n  Phase 3 v3 (103 gates, 4-qubit): 4.17×")
    print(f"  Phase 4   (12-qubit, row 78):     {amplification}×")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--transpile", action="store_true")
    parser.add_argument("--smoke",     action="store_true")
    parser.add_argument("--submit",    action="store_true")
    parser.add_argument("--results",   metavar="JOB_ID")
    parser.add_argument("--backend",   default=BACKEND_NAME)
    args = parser.parse_args()

    if args.results:
        get_results(args.results)
        sys.exit(0)

    print(f"\n7-qubit Grover  |  {N_SEARCH} rows  |  marked: {MARKED_ROWS}")

    if not verify_oracle():   sys.exit(1)
    if not verify_one_iter(): sys.exit(1)
    if not verify_full():     sys.exit(1)

    if args.transpile or args.smoke or args.submit:
        from qiskit_ibm_runtime import QiskitRuntimeService
        service = QiskitRuntimeService(channel="ibm_quantum_platform",
                                       token=os.getenv("IBM_QUANTUM_TOKEN"))
        backend = service.backend(args.backend)
        n_iter  = 1 if args.smoke else 4
        best_isa, best_total = transpile_check(backend, n_iter=n_iter)

        if (args.smoke or args.submit) and best_total > 450:
            print("\n❌ Circuit too deep — aborting. Optimise before submitting.")
            sys.exit(1)

        if args.smoke:
            submit_job(backend, best_isa, SHOTS_SMOKE, "SMOKE TEST — 1 iteration")
        elif args.submit:
            submit_job(backend, best_isa, SHOTS_FULL,  "FULL RUN — 4 iterations")
