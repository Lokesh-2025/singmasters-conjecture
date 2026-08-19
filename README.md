# Singmaster's Conjecture — Quantum Search on IBM Hardware

Exploring Singmaster's Conjecture using quantum amplitude amplification on real IBM quantum hardware. Fully automated pipeline: classical sieve → LNAA encoding → QPU execution.

**Singmaster's Conjecture:** No integer appears more than finitely many times in Pascal's Triangle. The known record is **8 appearances** — held by 3003. No number with 9+ appearances has ever been found.

Built on top of [quantum-hardware-mcp](https://github.com/Lokesh-2025/quantum-hardware-mcp) — an open-source MCP server giving AI assistants live access to 19 real quantum backends.

Collaboration with [Jack Woehr](https://www.linkedin.com/in/jackwoehr/) — IBM Quantum veteran, Qiskit contributor.

---

## Results Summary

| Experiment | Approach | Gates | Amplification | Backend | Status |
|------------|----------|-------|---------------|---------|--------|
| Phase 1 | Grover, 4 qubits, target=6 | 611 | 4.11× | ibm_kingston | ✅ |
| Phase 2 | Grover, 4 qubits, unoptimized | 16,271 | 1.04× | ibm_marrakesh | ❌ noise floor |
| Phase 3 v3 | Grover, 4 qubits, opt=2 seed=42 | 103 | 4.17× | ibm_marrakesh | ✅ |
| Phase 4 v1 | Grover, 7 qubits, rows 14+15+78 | 624 | 3.04× | ibm_marrakesh | ✅ row 78 found! |
| Phase 4 v2 | Grover, 7 qubits, lossy oracle | 1,037 | 1.92× | ibm_marrakesh | ❌ routing failure |
| Phase 5 | **LNAA**, 7 qubits, Ising walk | **135** | **27.78×** | ibm_marrakesh | ✅ record |
| Phase 6 | LNAA auto-collision, 9 qubits | 45 | 122.92× | simulation | ✅ |
| Step 3 | 3 parallel rails, 30 qubits | 180 | ~300× | ibm_kingston | ✅ **NEW RECORD** |
| Step 4 sim | 4-way collision, 24 qubits | 144 | 190.27× | simulation | ✅ |
| **Step 4 QPU** | **4-way collision, 24 qubits** | **144** | **178.8×** | **ibm_fez** | ✅ **HARDWARE RECORD** |

---

## The Big Result: First Hardware-Confirmed 4-Way Pascal Collision

**Job ID:** `d97fk8t2su3c739i26fg` — ibm_fez, 4096 shots

We submitted one circuit to a real quantum computer searching for 3003 across three Pascal columns simultaneously.

**Dominant bitstring:** `000011100000111101001110` → **1,396 shots (34.08%)**

Decoded rail by rail:
```
Rail k=6  bits 00001110  →  row 14   C(14,6) = 3003  ✓
Rail k=5  bits 00001111  →  row 15   C(15,5) = 3003  ✓
Rail k=2  bits 01001110  →  row 78   C(78,2) = 3003  ✓
```

All 3 targets confirmed simultaneously. Per-rail amplification: **~179×**. The 2nd-best state got 2.17% — the target is **25× cleaner than noise**.

Random baseline for this combined state: ~1 in 16 million. We got 34%.

---

## The Story

### Phase 1–3: Transpiler is the enemy

Phase 1 worked — 3.0× amplification on real hardware. Phase 2 pushed deeper: 101 logical gates became **16,271 transpiled gates** on IBM's heavy-hex topology (161× expansion). Signal collapsed.

Phase 3 attacked the transpiler: `generate_preset_pass_manager` at opt=2, oracle simplification (shared conditions → one CCZ replaces two MCX), ancilla-based RCCX diffusion, barrier removal. Result: **103 gates, 4.17×**.

### Phase 4: Routing failure diagnosed

Expanded to 7 qubits to find row 78 (C(78,2)=3003). Phase 4 v1 found it at 3.04×. Tried to optimize further — circuit exploded to 1,037 hardware gates.

Root cause: not the algorithm. **Graph embedding.** One ancilla qubit needed 4 direct connections. IBM heavy-hex allows max 3 per qubit. ~300 SWAP gates injected. Nothing inside Grover can fix this.

### Phase 5: Scrapped Grover. Built LNAA.

Derived an **Ising Hamiltonian** where rows 14, 15, 78 are the lowest energy states. IBM's RZZ and RX gates implement this natively — zero routing, zero SWAP, zero ancilla.

Result: **27.78× amplification with 135 hardware gates.** 6.7× better than the previous hardware record.

**Key insight:** IBM heavy-hex IS an Ising lattice. Encode targets as ground states, not Boolean conditions. Let the hardware topology be the algorithm.

### Phase 6: Zero manual design

Built `encode_collision_problem` — finds C(n1,k1)=C(n2,k2) pairs automatically from just k1,k2 inputs and encodes them as Ising coefficients. No circuit design. 122.92× in simulation.

### Step 3: Parallel rails, ~300× on hardware

Built `run_parallel_collision_search` — tiles multiple independent LNAA circuits across IBM's 156-qubit chip in ONE job. Three simultaneous searches (30 qubits total, 180 gates) on ibm_kingston. ~300× amplification — 10× better than Phase 5.

### Step 4: 4-Way Collision

Built `encode_4way_collision` — takes a value and its known positions from the sieve, builds one LNAA rail per k-column, submits all rails in one job.

190× in simulation → **179× on ibm_fez**. 94% hardware/simulation retention. All 3 k-columns fired simultaneously at 34% combined hit rate.

---

## Cross-hardware result: IBM vs IonQ, real hardware, same circuits (2026-08-19)

A separate, later experiment — not the collision search above, but the actual cross-vendor question the IonQ Research Credits grant was originally titled for ("Cross-Hardware Quantum Noise Benchmarking: IBM vs IonQ"). A graded-connectivity entangling circuit family (`single`, `ring`) was run for real on IonQ's Forte-Enterprise-1 first, then the identical circuits were run for real on `ibm_fez`:

| Circuit | IonQ (Forte-Enterprise-1) | IBM (`ibm_fez`) |
|---|---|---|
| **single** | 56.8x | 55.27x |
| **ring** | 15.7x | 20.38x |

`single` agrees almost exactly across two completely different qubit technologies (trapped ion vs. superconducting). `ring` doesn't — connectivity hurts more on IonQ than on IBM, a real, hardware-confirmed difference, not assumed from either vendor's noise model. A third circuit (`degree3`) was deliberately excluded from the IBM side: its required connectivity needs two triangles, and `ibm_fez`'s heavy-hex topology is provably triangle-free (checked directly against the real coupling map), so it can't map onto IBM without SWAP injection regardless of qubit choice.

Full narrative — real qubit selection, zero-SWAP verification, endianness cross-checks, and the two real tool bugs this work caught and fixed along the way — lives in the private [`ionq-singmasters`](https://github.com/Lokesh-2025/ionq-singmasters) repo, since it's built on top of the same real IonQ-side research documented there.

---

## The Pipeline

```
sieve_singmaster_space      ← classical, free, finds candidate positions
        ↓
encode_4way_collision       ← builds parallel LNAA rails automatically
        ↓
IBM QPU (one hardware job)  ← all k-columns searched simultaneously
        ↓
get_amplification           ← decodes bitstring, computes per-rail amp
```

All five stages run through the [quantum-hardware-mcp](https://github.com/Lokesh-2025/quantum-hardware-mcp) MCP server.

---

## Classical Sieve Results

`sieve_singmaster_space` uses Lucas' Theorem mod-prime fingerprinting to eliminate 98%+ of search space before touching the QPU.

| Run | max_n | max_k | 9+ found | 8-appearance values |
|-----|-------|-------|----------|---------------------|
| 1 | 500 | 50 | 0 | 3003 |
| 2 | 3003 | 200 | 0 | 3003 (all 8 positions validated) |
| 3 | 50,000 | 200 | 0 | 3003 only |

**3003 is the sole value with 8 appearances across 50,000 rows.** Everything else peaks at ≤6.

The 8 known positions of 3003:
```
C(14,6) = C(14,8) = C(15,5) = C(15,10) = C(78,2) = C(78,76) = C(3003,1) = C(3003,3002) = 3003
```

---

## Files

| File | Description |
|------|-------------|
| `results.txt` | Full raw results from all 11 hardware/simulation runs |
| `singmasters_grover.py` | Phase 1 — Grover, target=6 |
| `singmasters_3003.py` | Phase 2 — Grover, target=3003, coherence limit |
| `phase3_grover_v3.py` | Phase 3 v3 — 103 gates, 4.17× |
| `phase4_grover_7q.py` | Phase 4 v1 — 7 qubits, row 78 found |
| `phase4_grover_v2.py` | Phase 4 v2 — routing failure discovered |
| `phase5_lnaa.py` | Phase 5 — LNAA, 27.78× (record at time) |

New tools (Phases 6+) live in [quantum-hardware-mcp/server.py](https://github.com/Lokesh-2025/quantum-hardware-mcp/blob/master/server.py):
- `encode_collision_problem` — auto-finds C(n1,k1)=C(n2,k2) pairs, encodes as Ising Hamiltonian (122.92× in simulation)
- `run_parallel_collision_search` — tiles N independent LNAA rails across IBM's 156-qubit chip in one job (~300× on ibm_kingston)
- `sieve_singmaster_space` — Lucas theorem classical sieve, validated all 8 positions of 3003, searched n=2..50,000
- `encode_4way_collision` — multi-column parallel LNAA, **178.8× on ibm_fez** — hardware record
- `find_collision_candidates` — curve intersection search, integer root-finding across column pairs
- `equality_oracle_search` — two registers in superposition, cross-register RZZ amplifies pairs matching a Lucas mod-2 parity oracle, without being told which rows to look for. Parity match is a weak, ~50%-hit-rate filter, not proof of equality — classical post-processing (`comb()`) checks every measured pair for true equality. Confirmed C(16,2)=C(10,3)=120 this way.

---

## Key Observations

1. **Transpilation overhead** (161×) is the dominant challenge on heavy-hex topology
2. **Graph embedding** is the real bottleneck — not gate count, not the algorithm
3. **LNAA outperforms Grover** on heavy-hex: RZZ+RX are native gates, zero routing needed
4. **Parallel rails** let you run N searches in one hardware job — ibm_kingston has room for 10+
5. **Classical sieve first**: Lucas' theorem eliminates 98% of search space before QPU
6. **94% hardware/simulation retention** — LNAA results are highly predictable from simulation
7. **No 9+ value found** up to n=50,000 — consistent with Singmaster's Conjecture
8. If a 9+ value exists, it requires n > 50,000 and would itself be astronomically large
9. **Two-register LNAA works**: equality_oracle_search amplifies toward parity-matched pairs without being told which rows to check; classical post-processing confirms true equality — validates the two-register approach as a filter, not a standalone oracle
10. **Lucas predicate is classically cheap** — the quantum oracle's advantage is demonstrating the circuit construction on real hardware, not raw search speed over classical methods
