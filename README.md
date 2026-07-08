# Singmaster's Conjecture — Grover's Search on IBM Quantum

Exploring Singmaster's Conjecture using Grover's search algorithm on real IBM quantum hardware.

**Singmaster's Conjecture:** No number appears more than 12 times in Pascal's Triangle. The number 3003 holds the known record with 8 appearances — more than almost any other number. This project uses quantum search to find where 3003 hides.

## Results Summary

| Experiment | Gates | Amplification | Hardware | Status |
|------------|-------|---------------|----------|--------|
| Value 6, Phase 1 | 611 | 4.11× | ibm_kingston | ✅ |
| Value 3003, Phase 1 | 772 | 3.0× | ibm_kingston | ✅ |
| Value 3003, Phase 2 (coherence limit) | 16,271 | 1.04× | ibm_marrakesh | ❌ noise floor |
| Value 3003, Phase 3 v3 | **103** | **4.17×** | ibm_marrakesh | ✅ |

**Key finding:** 99.4% gate reduction (16,271 → 103) recovered the signal. The transpilation overhead on IBM's heavy-hex topology — not the algorithm — was the bottleneck.

## What We Found

Rows 14 and 15 of Pascal's Triangle both contain 3003:
- C(14,6) = 3003
- C(15,5) = 3003

On ibm_marrakesh (Phase 3 v3): rows 14 and 15 captured **52.1% of all shots** vs 12.5% random baseline = **4.17× quantum amplification**.

## The Story

**Phase 1:** Circuit worked. 3.0× amplification at 772 gates.

**Phase 2:** Pushed the circuit deeper to search more rows. 101 logical gates became **16,271 transpiled gates** on IBM's heavy-hex topology — a 161× expansion ratio. Signal collapsed to noise (1.04×).

**Phase 3:** Studied the transpiler and pass manager. Three optimizations:
1. `generate_preset_pass_manager` at opt=2 with seed sweep: 16,271 → 438 gates
2. Oracle simplification — rows 14 and 15 share condition q1=q2=q3=1, so one CCZ replaces two MCX calls
3. Ancilla-based RCCX diffusion + removed oracle/diffusion barrier so compiler cancels boundary gates

Result: **103 transpiled gates, 4.17× amplification on real hardware.**

## Files

| File | Description |
|------|-------------|
| `singmasters_grover.py` | Value 6 search, 4-qubit Grover (Phase 1 baseline) |
| `singmasters_3003.py` | Value 3003, Phases 1 and 2 |
| `phase3_grover.py` | Phase 3 v1 — transpiler benchmark (16,271 → 438 gates) |
| `phase3_grover_v2.py` | Phase 3 v2 — oracle simplification + ancilla diffusion (131 gates) |
| `phase3_grover_v3.py` | Phase 3 v3 — RCCX + barrier removal (103 gates) ← current best |
| `results.txt` | Full raw results from all hardware runs |

## Next Experiment

5-qubit Grover search (32 rows) — find additional appearances of 3003 beyond rows 14 and 15.

## Collaboration

Experiment conceived and run by [Lokesh Pullakandam](https://github.com/Lokesh-2025).
Collaboration with [Jack Woehr](https://www.linkedin.com/in/jackwoehr/) — IBM Quantum veteran, Qiskit contributor.

Built on top of [quantum-hardware-mcp](https://github.com/Lokesh-2025/quantum-hardware-mcp) — an open-source MCP server giving AI assistants live access to 19 real quantum backends.
