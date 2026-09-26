# IonQ Research Handoff: Singmaster's Conjecture

## Progress Summary
We have completed the **Pre-Flight Scouting and Simulation** phase. We established a strategy to maximize the $3,000 IonQ credit budget by batching three independent searches into a single $168 hardware job.

### 1. Hardware Status
- **Provider:** IonQ
- **Target QPU:** `forte-1` (36 qubits, all-to-all connectivity).
- **API Key:** Verified in local `.env` files.
- **Budget:** $3,000 (~17 hardware shots).

### 2. The "Triple-Rail" Batch Plan
To save money, we designed a single job containing three parallel search rails:
- **Rail 1 (Value 120):** Column 3 vs 7. Qubits: 10. **Simulated Signal: 348x amplification.**
- **Rail 2 (Value 220):** Column 3 vs 9. Qubits: 10. **Simulated Signal: 235x amplification.**
- **Rail 3 (Value 3003):** Column 5 vs 6. Qubits: 10. **Simulated Signal: 235x amplification.**

### 3. Circuit Parameters (LNAA Method)
These parameters are optimized for IonQ's native RZ/RZZ/RX gates:
- **Method:** Lattice-Native Amplitude Amplification (LNAA).
- **Gamma:** 2.589 (Phase angle).
- **Beta:** 0.501 (Mixing angle).
- **Layers (p):** 2.
- **Qubits per Rail:** 10 (Total 30 qubits used out of 36 available).

## Technical Blockers & Workarounds
- **MCP Tool Issue:** The `quantum-verifier` tool currently has trouble reading the `.env` file from the global node process.
- **Workaround:** Use the local virtual environment at `/Users/lokeshpullakandam/quantum-verifier/.venv/bin/python3` to run scripts directly. It has `qiskit`, `qiskit-ionq`, and `python-dotenv` installed.

## Next Steps for the Next Assistant
1. Use the `.venv` mentioned above to run a final **IonQ Noise Simulation**.
2. If noise simulation passes, submit the batch using `ionq_submit_job` or a custom Qiskit script.
3. Compare the "Quantum Lift" (signal) against a control circuit to prove the collision discovery.
