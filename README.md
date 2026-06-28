# Singmaster's Conjecture — Grover's Search on IBM Quantum

Exploring Singmaster's Conjecture using Grover's search algorithm on real IBM quantum hardware.

**Singmaster's Conjecture:** Does any number appear 9 or more times in Pascal's Triangle?

## Approach

We use Grover's search to find which rows of Pascal's Triangle contain a target value.
Each qubit register encodes row indices. The oracle marks rows where the value appears.

## Experiments

### Experiment 1 — Value 6 (2 marked states, 4 qubits)
- Search space: rows 0-15 (2^4 = 16 states)
- Marked: row 4 (C(4,2)=6) and row 6 (C(6,1)=6)
- Grover iterations: 2
- Backend: ibm_kingston
- Circuit depth after transpile: 611

**Results (job d90ie8g6c68s73ai4e9g):**
```
|0110⟩ (row  6):  275 shots ( 26.9%) ← MARKED
|0100⟩ (row  4):  247 shots ( 24.1%) ← MARKED
|1011⟩ (row 11):   51 shots (  5.0%)
|1010⟩ (row 10):   50 shots (  4.9%)
...

Marked rows combined: 522/1024 shots = 51.0%
Uniform random would give: 12.4%
Grover amplification factor: 4.11x
✅ SUCCESS
```

### Experiment 2 — Value 3003, Phase 1 (2 marked states, 4 qubits)
- Search space: rows 0-15 (2^4 = 16 states)
- Marked: row 14 (C(14,6)=3003) and row 15 (C(15,5)=3003)
- Grover iterations: 2
- Backend: ibm_kingston
- Circuit depth after transpile: 772

**Results (job d90iiq86c68s73ai4jfg):**
```
|1111⟩ (row 15):  196 shots ( 19.1%) ← MARKED
|1110⟩ (row 14):  185 shots ( 18.1%) ← MARKED
|0110⟩ (row  6):   57 shots (  5.6%)
...

Marked rows combined: 381/1024 = 37.2%
Uniform random: 12.4%
Amplification: 3.0x
✅ SUCCESS
```

### Experiment 3 — Value 3003, Phase 2 (3 marked states, 7 qubits)
- Search space: rows 0-127 (2^7 = 128 states)
- Marked: rows 14, 15, 78 (C(78,2)=3003)
- Status: **PENDING** — to be discussed Monday

## Observations

1. Grover's amplification degrades with circuit depth (4.11x at depth 611 → 3.0x at depth 772)
2. Both experiments succeeded on real hardware despite significant noise
3. Deeper circuits (7 qubits, depth ~1500) may lose signal — to be evaluated

## Next Steps (Monday discussion with Jack)
- Run Phase 2 on simulator to verify circuit correctness
- Decide if real hardware run is worth remaining QPU minutes
- IonQ comparison once credits approved

## Files
- `singmasters_grover.py` — value 6, two-target Grover's (4 qubits)
- `singmasters_3003.py` — value 3003, phases 1 and 2
