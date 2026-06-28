"""
singmasters_3003.py
-------------------
Grover's search for 3003 in Pascal's Triangle — scale-up experiment.

3003 appears 6 times in Pascal's Triangle:
    C(3003, 1) = 3003  → row 3003  (too large for current hardware)
    C(78,   2) = 3003  → row 78    (needs 7 qubits)
    C(15,   5) = 3003  → row 15    (4 qubits)
    C(15,  10) = 3003  → row 15    (same row, symmetric)
    C(14,   6) = 3003  → row 14    (4 qubits)
    C(14,   8) = 3003  → row 14    (same row, symmetric)

This experiment runs TWO phases:
    Phase 1 (4 qubits): search rows 0-15, find rows 14 and 15
    Phase 2 (7 qubits): search rows 0-127, find rows 14, 15, AND 78

Run phase 1 first — it's cheaper and verifies the approach before scaling.

Usage:
    python experiments/singmasters_3003.py --phase 1       # submit phase 1
    python experiments/singmasters_3003.py --phase 2       # submit phase 2
    python experiments/singmasters_3003.py --results ID    # get results
    python experiments/singmasters_3003.py --status ID     # check status
"""

import os
import sys
import math
import argparse

from dotenv import load_dotenv
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../.env"))

from qiskit import QuantumCircuit
from qiskit.transpiler.preset_passmanagers import generate_preset_pass_manager
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2 as Sampler

TARGET_VALUE = 3003

PHASES = {
    1: {
        "n_qubits": 4,
        "marked_rows": [14, 15],
        "marked_states": ["1110", "1111"],
        "description": "rows 0-15 (4 qubits) — finds C(14,6) and C(15,5)",
    },
    2: {
        "n_qubits": 7,
        "marked_rows": [14, 15, 78],
        "marked_states": ["0001110", "0001111", "1001110"],
        "description": "rows 0-127 (7 qubits) — finds C(14,6), C(15,5), AND C(78,2)",
    },
}

SHOTS = 1024


def build_oracle(qc, marked_states, n_qubits):
    for state in marked_states:
        for i, bit in enumerate(reversed(state)):
            if bit == "0":
                qc.x(i)
        qc.h(n_qubits - 1)
        qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
        qc.h(n_qubits - 1)
        for i, bit in enumerate(reversed(state)):
            if bit == "0":
                qc.x(i)
        qc.barrier()


def build_diffusion(qc, n_qubits):
    qc.h(range(n_qubits))
    qc.x(range(n_qubits))
    qc.h(n_qubits - 1)
    qc.mcx(list(range(n_qubits - 1)), n_qubits - 1)
    qc.h(n_qubits - 1)
    qc.x(range(n_qubits))
    qc.h(range(n_qubits))
    qc.barrier()


def build_circuit(phase_cfg):
    n_qubits = phase_cfg["n_qubits"]
    marked_states = phase_cfg["marked_states"]
    n_marked = len(marked_states)
    n_iterations = max(1, math.floor(
        math.pi / 4 * math.sqrt((2**n_qubits) / n_marked)
    ))

    qc = QuantumCircuit(n_qubits, n_qubits)
    qc.h(range(n_qubits))
    qc.barrier()

    for _ in range(n_iterations):
        build_oracle(qc, marked_states, n_qubits)
        build_diffusion(qc, n_qubits)

    qc.measure(range(n_qubits), range(n_qubits))
    return qc, n_iterations


def submit(phase_num, backend_name=None):
    phase_cfg = PHASES[phase_num]
    n_qubits = phase_cfg["n_qubits"]
    marked_rows = phase_cfg["marked_rows"]
    marked_states = phase_cfg["marked_states"]

    token = os.getenv("IBM_QUANTUM_TOKEN")
    if not token:
        print("ERROR: IBM_QUANTUM_TOKEN not set in .env")
        sys.exit(1)

    service = QiskitRuntimeService(channel="ibm_quantum_platform", token=token)

    if backend_name:
        backend = service.backend(backend_name)
    else:
        backends = [b for b in service.backends(operational=True)
                    if b.num_qubits >= n_qubits]
        backend = min(backends, key=lambda b: b.status().pending_jobs)

    qc, n_iterations = build_circuit(phase_cfg)

    print(f"\n{'='*60}")
    print(f"Singmaster's — Grover's Search for {TARGET_VALUE}")
    print(f"Phase {phase_num}: {phase_cfg['description']}")
    print(f"{'='*60}")
    print(f"Marked rows:   {marked_rows}")
    print(f"Marked states: {marked_states}")
    print(f"Search space:  {2**n_qubits} rows")
    print(f"Grover iters:  {n_iterations}")
    print(f"Backend:       {backend.name}")
    print(f"Shots:         {SHOTS}")
    print(f"{'='*60}\n")

    print(f"Circuit depth (before transpile): {qc.depth()}")

    pm = generate_preset_pass_manager(backend=backend, optimization_level=1)
    isa = pm.run(qc)
    print(f"Circuit depth (after transpile):  {isa.depth()}\n")

    sampler = Sampler(backend)
    job = sampler.run([isa], shots=SHOTS)
    job_id = job.job_id()

    print(f"Job submitted! ID: {job_id}")
    print(f"\npython experiments/singmasters_3003.py --results {job_id}")


def get_status(job_id):
    service = QiskitRuntimeService(
        channel="ibm_quantum_platform",
        token=os.getenv("IBM_QUANTUM_TOKEN")
    )
    print(f"Job {job_id}: {service.job(job_id).status()}")


def get_results(job_id, phase_num=1):
    phase_cfg = PHASES[phase_num]
    marked_rows = phase_cfg["marked_rows"]
    marked_states = phase_cfg["marked_states"]
    n_qubits = phase_cfg["n_qubits"]

    service = QiskitRuntimeService(
        channel="ibm_quantum_platform",
        token=os.getenv("IBM_QUANTUM_TOKEN")
    )
    job = service.job(job_id)
    result = job.result()
    pub_result = result[0]
    bitarray = pub_result.data
    field = list(vars(bitarray).keys())[0]
    counts = getattr(bitarray, field).get_counts()
    total = sum(counts.values())

    print(f"\n{'='*60}")
    print(f"Singmaster's 3003 — Results (job {job_id})")
    print(f"Phase {phase_num}: {phase_cfg['description']}")
    print(f"{'='*60}")
    print(f"\nTop 10 measured states:")

    for state, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]:
        row = int(state, 2)
        pct = round(count / total * 100, 1)
        bar = "█" * int(pct / 2)
        marker = " ← MARKED!" if row in marked_rows else ""
        print(f"  |{state}⟩ (row {row:3d}): {count:4d} shots ({pct:5.1f}%) {bar}{marker}")

    marked_total = sum(counts.get(s, 0) for s in marked_states)
    marked_pct = round(marked_total / total * 100, 1)
    uniform_pct = round(100 / (2**n_qubits), 1)
    combined_uniform = round(uniform_pct * len(marked_states), 1)
    amplification = round(marked_pct / combined_uniform, 2) if combined_uniform > 0 else 0

    print(f"\n{'='*60}")
    print(f"Marked rows combined: {marked_total}/{total} = {marked_pct}%")
    print(f"Uniform random:       {combined_uniform}%")
    print(f"Amplification:        {amplification}x")

    for state, row in zip(marked_states, marked_rows):
        print(f"  Row {row}: {counts.get(state, 0)} shots")

    if marked_pct > combined_uniform * 1.5:
        print(f"\n✅ SUCCESS — Grover's found {TARGET_VALUE} at rows {marked_rows}!")
    else:
        print(f"\n⚠️  NOISY — circuit too deep for clean signal. Try fewer qubits or optimization_level=3.")

    print(f"\nNext: Phase 2 (7 qubits) to find C(78,2)=3003 at row 78.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, default=1, choices=[1, 2])
    parser.add_argument("--backend", help="IBM backend name")
    parser.add_argument("--status", metavar="JOB_ID")
    parser.add_argument("--results", metavar="JOB_ID")
    args = parser.parse_args()

    if args.status:
        get_status(args.status)
    elif args.results:
        get_results(args.results, args.phase)
    else:
        submit(args.phase, args.backend)
