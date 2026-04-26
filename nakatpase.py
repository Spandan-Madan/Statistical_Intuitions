"""
Single Na/K-ATPase pump cycle - stochastic Gillespie simulation.

Hardware-vs-software comparison:
    Biology runs this algorithm using ~50 kJ/mol of ATP free energy per cycle.
    Silicon runs the same algorithm using (wall_clock_time x CPU_power) per cycle.

Model:    Linear forward Post-Albers cycle, 11 states.
Rates:    Heyse, Wuddel, Apell & Stuermer (1994) Table V, T = 20 C.
Substrates (folded into effective rates below):
    [Na+]_cyto = 10 mM,  [Na+]_ext = 140 mM
    [K+]_cyto  = 140 mM, [K+]_ext  = 5 mM
    [ATP]      = 5 mM,   [ADP]     = 50 uM,  [Pi] = 1 mM

Run:
    python nakatpase.py
"""

import time
import numpy as np


# ---------------------------------------------------------------------------
# Effective rate constants at physiological substrate concentrations, T=20C
# Each pair (kf, kb) is the forward and backward rate for one transition.
# Bimolecular rates have already been multiplied by the relevant [substrate].
# Units: s^-1
# ---------------------------------------------------------------------------
TRANSITIONS = [
    # ( kf,         kb,         label )
    ( 2.0e3,        8.0e2,      "E1            -> Na3.E1         (cyto Na+ binds 3rd site)" ),
    ( 7.5e4,        1.64,       "Na3.E1        -> Na3.E1.ATP     (ATP binds, high affinity)" ),
    ( 2.0e2,        18.5,       "Na3.E1.ATP    -> (Na3)E1-P      (phosphorylation, ADP off)" ),
    ( 22.0,         25.2,       "(Na3)E1-P     -> P-E2(Na2)      (CONFORMATIONAL FLIP, 1st Na out) [rate-limiting]" ),
    ( 5.0e3,        375.2,      "P-E2(Na2)     -> P-E2(Na)       (2nd Na out)" ),
    ( 1.0e5,        1.4e5,      "P-E2(Na)      -> P-E2           (3rd Na out)" ),
    ( 1.7e2,        10.0,       "P-E2          -> P-E2(K)        (1st K binds from outside)" ),
    ( 2.5e4,        2.0e3,      "P-E2(K)       -> P-E2(K2)       (2nd K binds)" ),
    ( 1.0e3,        5.0e3,      "P-E2(K2)      -> E2(K2)         (K occlusion + dephos, Pi off)" ),
    ( 2.5e3,        4.0,        "E2(K2)        -> ATP.E2(K2)     (ATP binds, low affinity)" ),
    ( 22.0,         400.0,      "ATP.E2(K2)    -> E1             (CONFORMATIONAL FLIP back, K released to cyto) [rate-limiting]" ),
]
N = len(TRANSITIONS)   # 11 transitions, 11 states (state N == state 0)
KF = np.array([t[0] for t in TRANSITIONS])
KB = np.array([t[1] for t in TRANSITIONS])


# ---------------------------------------------------------------------------
# Indexing convention:
#   TRANSITIONS[i] = (kf_i, kb_i) describes the bond between state i and i+1.
#     kf_i = rate of the forward step  i   ->  i+1
#     kb_i = rate of the backward step i+1 ->  i
#   At state s, the molecule can:
#     - step forward  to s+1 at rate KF[s]
#     - step backward to s-1 at rate KB[(s-1) mod N]      <-- note the offset
#   (Going backward FROM state s uses the backward rate of the transition
#    that LANDS on state s, which is transition s-1.)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Gillespie: simulate one molecule until it completes one net forward cycle.
# `net_progress` increments on forward steps, decrements on backward steps.
# When net_progress reaches N, the molecule has completed one full cycle
# and hydrolyzed exactly one ATP.
# ---------------------------------------------------------------------------
def simulate_one_cycle(rng):
    state = 0
    t = 0.0
    net_progress = 0
    n_steps = 0
    while net_progress < N:
        kf = KF[state]
        kb = KB[(state - 1) % N]   # backward rate of transition s-1
        k_total = kf + kb
        # Time to next event: exponential with rate k_total
        dt = -np.log(rng.random()) / k_total
        t += dt
        # Which event fires?
        if rng.random() < kf / k_total:
            state = (state + 1) % N
            net_progress += 1
        else:
            state = (state - 1) % N
            net_progress -= 1
        n_steps += 1
    return t, n_steps


# ---------------------------------------------------------------------------
# Analytical steady-state turnover for a unicyclic Markov chain.
# Solves the master equation exactly given (KF, KB), returning the cycle
# flux J (cycles per second per molecule) and the steady-state probabilities.
# This is the ground truth that the Gillespie simulation should converge to.
# ---------------------------------------------------------------------------
def steady_state_flux(kf, kb):
    n = len(kf)
    # Parametrize P_i = A_i - B_i * J  with P_0 = 1 (un-normalized).
    A = np.empty(n + 1)
    B = np.empty(n + 1)
    A[0], B[0] = 1.0, 0.0
    for i in range(n):
        # P_{i+1} = (kf_i * P_i - J) / kb_i
        A[i + 1] = (kf[i] / kb[i]) * A[i]
        B[i + 1] = (kf[i] / kb[i]) * B[i] + 1.0 / kb[i]
    # Cyclicity: P_n = P_0 = 1   =>   A_n - B_n * J = 1
    J_unnorm = (A[n] - 1.0) / B[n]
    P_unnorm = A[:n] - B[:n] * J_unnorm
    Z = P_unnorm.sum()
    P = P_unnorm / Z
    J = J_unnorm / Z   # cycles per second per molecule
    return J, P


# ---------------------------------------------------------------------------
# Run many independent cycles and time the wall-clock cost
# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("Na/K-ATPase single-cycle Gillespie simulation")
    print("=" * 70)

    print("\nForward and backward rates (s^-1) at 20 C, physiological substrates:")
    for i, (kf, kb, lbl) in enumerate(TRANSITIONS):
        print(f"  [{i:2d}] kf={kf:9.2e}  kb={kb:9.2e}  {lbl}")

    # Analytical ground truth (steady-state master-equation solution)
    J_analytic, P_ss = steady_state_flux(KF, KB)
    print(f"\nAnalytical steady-state turnover:  {J_analytic:8.2f} s^-1")
    print(f"Analytical mean cycle time:        {1.0/J_analytic*1e3:8.2f} ms")

    n_trials = 100_000
    rng = np.random.default_rng(42)

    print(f"\nRunning {n_trials:,} independent single-cycle simulations...")
    t0 = time.perf_counter()
    cycle_times = np.empty(n_trials)
    step_counts = np.empty(n_trials, dtype=np.int64)
    for i in range(n_trials):
        cycle_times[i], step_counts[i] = simulate_one_cycle(rng)
    wall_clock = time.perf_counter() - t0

    # ---- Biology side ----
    KJ_PER_MOL_ATP = 50.0           # physiological ATP hydrolysis dG (kJ/mol)
    N_AVOGADRO     = 6.02214076e23
    J_PER_ATP      = KJ_PER_MOL_ATP * 1e3 / N_AVOGADRO   # ~8.3e-20 J
    bio_J_per_cycle = J_PER_ATP

    # ---- Silicon side ----
    # Energy = wall_clock * CPU_power (active draw during this run).
    # Set CPU_POWER_W to the active power draw of YOUR machine.
    # Examples (active, single core saturated):
    #   Apple M1 Pro:  ~10 W package power  (use `powermetrics` to measure)
    #   Apple M2 Max:  ~15 W package power
    #   Intel i7-12700K: ~30-50 W package power
    #   Intel Xeon Gold: ~50-150 W package power
    # If unsure, 15 W is a reasonable laptop figure for active CPU.
    CPU_POWER_W = 15.0

    si_wall_per_cycle = wall_clock / n_trials                  # seconds
    si_J_per_cycle    = si_wall_per_cycle * CPU_POWER_W        # joules

    # ---- Biology: real time per cycle (the molecule's own clock) ----
    bio_real_time_per_cycle = cycle_times.mean()               # seconds
    turnover = 1.0 / bio_real_time_per_cycle                   # s^-1

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)

    print(f"\n--- Simulation diagnostics ---")
    print(f"  Mean simulated cycle time (biological):  {bio_real_time_per_cycle*1e3:8.2f} ms")
    print(f"  Median simulated cycle time:             {np.median(cycle_times)*1e3:8.2f} ms")
    print(f"  Implied turnover rate (20 C):            {turnover:8.2f} s^-1")
    print(f"  Heyse 1994 measured at 37 C:                60 - 85 s^-1")
    print(f"  Q10~3 scaled to 20 C:                       ~7 - 10 s^-1")
    print(f"  Mean transitions per cycle:              {step_counts.mean():8.1f}")

    print(f"\n--- Biology: energy per cycle ---")
    print(f"  1 ATP hydrolyzed at dG = {KJ_PER_MOL_ATP:.0f} kJ/mol")
    print(f"  E_bio = {bio_J_per_cycle:.3e} J / cycle")

    print(f"\n--- Silicon: energy per cycle ---")
    print(f"  Wall-clock time for {n_trials:,} cycles: {wall_clock:.3f} s")
    print(f"  Wall-clock time per cycle:           {si_wall_per_cycle*1e6:.3f} us")
    print(f"  Assumed CPU active power:            {CPU_POWER_W:.1f} W")
    print(f"  E_si  = {si_J_per_cycle:.3e} J / cycle")

    print(f"\n--- Hardware efficiency ratio ---")
    print(f"  E_si / E_bio = {si_J_per_cycle / bio_J_per_cycle:.3e}")
    print(f"  (Silicon spends ~{si_J_per_cycle/bio_J_per_cycle:.0e}x more energy")
    print(f"   to simulate one cycle than biology spends to perform one.)")

    print()


if __name__ == "__main__":
    main()
