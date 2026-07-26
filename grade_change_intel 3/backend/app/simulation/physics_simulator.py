"""
physics_simulator.py
DR-11: physics-informed synthetic grade-transition generator.

Not a demo prop -- it is the only way (per A-1's fallback) to generate labelled
failure transitions in volume, and failures are the minority class that drives
M-1. Every quality variable is produced by an actual dynamic model, not a curve
fit to look plausible:

  * BW, ash follow a MASS-BALANCE forcing function (stock/filler flow x
    consistency/retention, divided by speed x trim width) pushed through a
    discrete FOPDT (dead time theta, time constant tau) response -- this is
    what makes "predict ahead" a real problem: the forcing function changes
    the instant the ramp starts, but the *measured* BW only catches up theta
    seconds later, low-pass filtered by tau.
  * Moisture follows a steam/speed drying-capacity model with an explicit
    saturation nonlinearity (when required drying capacity exceeds what the
    steam header can deliver, moisture forcing rises above target and stays
    there -- this is a real papermaking phenomenon, not noise).
  * Six independently-injectable faults create genuine failure diversity:
    steam_header_saturation, retention_drop, sheet_break,
    scanner_standardization_gap, consistency_upset, stuck_actuator.
  * BW_SP(t) is modelled as the Controller's own ramping trajectory
    (S-curve), separate from measured BW -- off-spec is evaluated against
    THIS trajectory (PRD Sec 1.3 / DR-07), not the final grade target, which
    is the correctness bug the previous prototype had.

Deterministic: every call with the same seed produces byte-identical output
(NFR-7, NFR-14).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)

DT_S = 5                 # DR-06 canonical resample grid
WINDOW_MIN = 22
N = int(WINDOW_MIN * 60 / DT_S)          # 264 samples
RAMP_START_IDX = 36                      # t=180s: 3 min PRE_CHECK baseline
RAMP_END_IDX = 132                       # t=660s: 8-minute coordinated ramp
TRIM_WIDTH = 8.5                         # m, machine constant
SPEED_NOMINAL = 900.0                    # mpm
STEAM_NOMINAL = 42.0                     # kPa, baseline drying capacity reference
MASS_K_BW = 2332.0                       # BW mass-balance calibration constant
MASS_K_ASH = 7400.0                      # Ash mass-balance calibration constant

GRADES = {
    # target_*: steady-state grade targets. retention/ash_retention: fraction
    # of stock/filler mass retained on the wire (grade-dependent per DR-11).
    # consistency: headbox stock consistency (%). theta_s: per-grade BW
    # transport dead time (A-4), varies with furnish/speed regime per grade.
    "GradeA": {"target_bw": 80, "target_moisture": 6.0, "target_ash": 12.0, "target_caliper": 120,
               "retention": 0.82, "ash_retention": 0.58, "consistency": 3.2, "theta_s": 22},
    "GradeB": {"target_bw": 95, "target_moisture": 6.5, "target_ash": 15.0, "target_caliper": 140,
               "retention": 0.85, "ash_retention": 0.62, "consistency": 3.4, "theta_s": 25},
    "GradeC": {"target_bw": 70, "target_moisture": 5.5, "target_ash": 10.0, "target_caliper": 100,
               "retention": 0.80, "ash_retention": 0.55, "consistency": 3.0, "theta_s": 20},
    "GradeD": {"target_bw": 110, "target_moisture": 7.0, "target_ash": 18.0, "target_caliper": 160,
               "retention": 0.88, "ash_retention": 0.66, "consistency": 3.6, "theta_s": 28},
}
GRADE_NAMES = list(GRADES.keys())

FAULT_TYPES = [
    "steam_header_saturation", "retention_drop", "sheet_break",
    "scanner_standardization_gap", "consistency_upset", "stuck_actuator",
]


def smoothstep(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 0, 1)
    return 3 * p ** 2 - 2 * p ** 3


def fopdt(forcing: np.ndarray, dt: float, theta_s: float, tau_s: float, y0: float) -> np.ndarray:
    """Discrete first-order-plus-dead-time response of `forcing` -> output.
    y[k] = y[k-1] + (dt/tau) * (forcing[k - theta_idx] - y[k-1])
    """
    theta_idx = max(int(round(theta_s / dt)), 0)
    delayed = np.concatenate([np.full(theta_idx, forcing[0]), forcing])[: len(forcing)]
    y = np.empty_like(forcing, dtype=float)
    y[0] = y0
    alpha = dt / max(tau_s, dt)
    for k in range(1, len(forcing)):
        y[k] = y[k - 1] + alpha * (delayed[k] - y[k - 1])
    return y


def nominal_manipulated(grade: dict) -> dict:
    """Invert the steady-state mass balance to get the manipulated-variable
    nominal that would, at SPEED_NOMINAL, produce this grade's targets."""
    stock_flow = grade["target_bw"] * SPEED_NOMINAL * TRIM_WIDTH / (MASS_K_BW * grade["consistency"] * grade["retention"])
    filler_flow = grade["target_ash"] * SPEED_NOMINAL * TRIM_WIDTH / (MASS_K_ASH * grade["ash_retention"])
    steam_pressure = STEAM_NOMINAL * (grade["target_moisture"] / 6.5)
    return {"stock_flow": stock_flow, "filler_flow": filler_flow,
            "steam_pressure": steam_pressure, "machine_speed": SPEED_NOMINAL}


def simulate_transition(event_id: str, from_grade: str, to_grade: str, rng: np.random.Generator,
                         inject_fault: str | None = None) -> dict:
    src, dst = GRADES[from_grade], GRADES[to_grade]
    src_nom, dst_nom = nominal_manipulated(src), nominal_manipulated(dst)
    t = np.arange(N) * DT_S

    # Per-event execution quality: how tightly the loops are tuned/operated for
    # THIS transition (Sec 1.1: "experienced operator knowledge is scarce" --
    # skill shortages are a named driver of transition variance, not measurement
    # noise). Higher = faster convergence. Affects response TIME CONSTANTS
    # (how well-executed the transition is), never the transport dead time
    # theta, which is a fixed physical property of the machine, not of execution.
    responsiveness = rng.uniform(0.35, 2.2)

    progress_raw = np.clip((np.arange(N) - RAMP_START_IDX) / (RAMP_END_IDX - RAMP_START_IDX), 0, 1)
    progress = smoothstep(progress_raw)  # S-curve trajectory calc, matches real coordinated ramps

    def ramp(src_v, dst_v):
        return src_v + (dst_v - src_v) * progress

    # ---- SP trajectories (what the Controller PUBLISHES, incl. BW_SP) ----
    stock_flow_sp = ramp(src_nom["stock_flow"], dst_nom["stock_flow"])
    filler_flow_sp = ramp(src_nom["filler_flow"], dst_nom["filler_flow"])
    steam_pressure_sp = ramp(src_nom["steam_pressure"], dst_nom["steam_pressure"])
    machine_speed_sp = ramp(src_nom["machine_speed"], dst_nom["machine_speed"])
    bw_sp = ramp(src["target_bw"], dst["target_bw"])  # sec 1.3 / DR-07: off-spec measured vs THIS

    # ---- PV tracking of SP (fast inner actuator loops, tau~12s) ----
    noise = lambda scale: rng.normal(0, scale, N)
    stock_flow = fopdt(stock_flow_sp, DT_S, 5, 12, stock_flow_sp[0]) + noise(0.5)
    filler_flow = fopdt(filler_flow_sp, DT_S, 5, 12, filler_flow_sp[0]) + noise(0.2)
    steam_pressure = fopdt(steam_pressure_sp, DT_S, 5, 12, steam_pressure_sp[0]) + noise(0.3)
    machine_speed = fopdt(machine_speed_sp, DT_S, 5, 10, machine_speed_sp[0]) + noise(2.0)
    # Referenced (not copied) by the stuck_actuator fault below: mutating mv[tag] in
    # place mutates the same ndarray the stock_flow/filler_flow/... names point to.
    mv = {"stock_flow": stock_flow, "filler_flow": filler_flow,
          "steam_pressure": steam_pressure, "machine_speed": machine_speed}

    # ---- context / disturbance ----
    consistency = ramp(src["consistency"], dst["consistency"]) + noise(0.03)
    retention_aid_flow = ramp(6.0, 6.0) + noise(0.15)          # nominal, small drift
    retention = np.full(N, dst["retention"])
    retention[:RAMP_START_IDX] = src["retention"]
    retention = fopdt(retention, DT_S, 8, 20 / responsiveness, src["retention"])
    ash_retention = np.full(N, dst["ash_retention"])
    ash_retention[:RAMP_START_IDX] = src["ash_retention"]
    ash_retention = fopdt(ash_retention, DT_S, 8, 20 / responsiveness, src["ash_retention"])
    dryer_hood_humid = np.clip(45 + rng.normal(0, 8), 20, 80) + noise(0.5)  # per-event constant-ish
    broke_ratio = np.clip(8 + noise(1.0), 0, 30)

    quality = {tag: np.full(N, "GOOD", dtype=object) for tag in
               ["BW_MEAS", "MOIST_MEAS", "ASH_MEAS", "CALIPER_MEAS"]}
    scanner_valid = np.ones(N, dtype=bool)
    scanner_standardizing = np.zeros(N, dtype=bool)
    sheet_break_flag = np.zeros(N, dtype=bool)
    alarms = []

    # ------------------------------------------------------------------
    # Fault injection (DR-11) -- each mutates the physically-relevant
    # signal(s) so the effect on BW/ash/moisture is a genuine causal
    # consequence, not a label-only flag.
    # ------------------------------------------------------------------
    if inject_fault == "steam_header_saturation":
        w0, w1 = RAMP_START_IDX, min(RAMP_START_IDX + 30, N)
        steam_max = STEAM_NOMINAL * 1.15
        steam_pressure[w0:w1] = np.minimum(steam_pressure[w0:w1], steam_max)
        alarms.append((t[w0], "STEAM_HEADER_SATURATED"))

    elif inject_fault == "retention_drop":
        w0, w1 = RAMP_START_IDX + 10, min(RAMP_START_IDX + 70, N)
        drop = rng.uniform(0.15, 0.30)
        retention[w0:w1] *= (1 - drop)
        ash_retention[w0:w1] *= (1 - drop * 0.6)
        retention_aid_flow[w0:w1] *= (1 - drop * 0.8)  # observable proxy -> discoverable correlation
        alarms.append((t[w0], "RETENTION_UPSET"))

    elif inject_fault == "consistency_upset":
        w0 = int(rng.integers(10, N - 30))
        w1 = w0 + int(rng.integers(15, 30))
        consistency[w0:w1] *= rng.choice([0.75, 1.25])
        alarms.append((t[w0], "CONSISTENCY_UPSET"))

    elif inject_fault == "stuck_actuator":
        stuck_tag = rng.choice(["stock_flow", "filler_flow", "steam_pressure", "machine_speed"])
        w0, w1 = RAMP_START_IDX, N
        mv[stuck_tag][w0:w1] = mv[stuck_tag][w0]  # freeze at pre-ramp value (mutates shared array)
        alarms.append((t[w0], f"ACTUATOR_STUCK:{stuck_tag}"))
    else:
        stuck_tag = None

    if inject_fault == "scanner_standardization_gap":
        w0 = int(rng.integers(RAMP_START_IDX, RAMP_START_IDX + 60))
        w1 = w0 + int(rng.integers(8, 18))  # 40-90s
        scanner_valid[w0:w1] = False
        scanner_standardizing[w0:w1] = True
        for tag in quality:
            quality[tag][w0:w1] = "STALE"
        alarms.append((t[w0], "SCANNER_STANDARDIZING"))

    sheet_break_idx = None
    if inject_fault == "sheet_break":
        sheet_break_idx = int(rng.integers(RAMP_START_IDX + 5, RAMP_END_IDX))
        sheet_break_flag[sheet_break_idx:] = True
        machine_speed[sheet_break_idx:] *= 0.15
        for tag in quality:
            quality[tag][sheet_break_idx:min(sheet_break_idx + 12, N)] = "BAD"
        alarms.append((t[sheet_break_idx], "SHEET_BREAK"))

    # ---- Mass-balance forcing -> FOPDT response (the actual physics) ----
    bw_forcing = MASS_K_BW * stock_flow * consistency * retention / (machine_speed * TRIM_WIDTH)
    theta_bw = 0.5 * (src["theta_s"] + dst["theta_s"])
    basis_weight = fopdt(bw_forcing, DT_S, theta_bw, 40 / responsiveness, bw_forcing[0])

    ash_forcing = MASS_K_ASH * filler_flow * ash_retention / (machine_speed * TRIM_WIDTH)
    ash = fopdt(ash_forcing, DT_S, theta_bw * 0.8, 35 / responsiveness, ash_forcing[0])

    # ---- Moisture: drying-capacity saturation nonlinearity ----
    drying_capacity = np.clip(steam_pressure / STEAM_NOMINAL, 0.5, 1.4)
    required_drying = np.clip(machine_speed / SPEED_NOMINAL, 0.7, 1.4)
    dst_moisture = np.full(N, dst["target_moisture"])
    dst_moisture[:RAMP_START_IDX] = src["target_moisture"]
    moist_forcing = dst_moisture + 1.8 * np.maximum(0, required_drying - drying_capacity)
    moisture = fopdt(moist_forcing, DT_S, 15, 110, src["target_moisture"])

    # ---- Caliper: secondary, driven off BW/ash deviation ----
    dst_caliper = np.full(N, dst["target_caliper"])
    dst_caliper[:RAMP_START_IDX] = src["target_caliper"]
    caliper_forcing = dst_caliper + 3.0 * (basis_weight - bw_forcing[-1]) / max(bw_forcing[-1], 1) * 100 * 0.05
    caliper = fopdt(caliper_forcing, DT_S, 10, 60, src["target_caliper"]) + noise(0.8)

    basis_weight = basis_weight + noise(0.35)
    ash = ash + noise(0.12)
    moisture = moisture + noise(0.06)

    if sheet_break_idx is not None:
        basis_weight[sheet_break_idx:min(sheet_break_idx + 12, N)] = np.nan
        moisture[sheet_break_idx:min(sheet_break_idx + 12, N)] = np.nan
        ash[sheet_break_idx:min(sheet_break_idx + 12, N)] = np.nan

    # ---- Off-spec per Sec 1.3: measured vs the RAMPING setpoint, not final target ----
    bw_dev_pct = 100 * (basis_weight - bw_sp) / bw_sp
    off_spec = (np.abs(bw_dev_pct) > 2.5)
    persist_scans = 3
    sustained_off_spec = pd.Series(off_spec).rolling(persist_scans).apply(lambda w: w.all()).fillna(False).astype(bool).values

    # ---- T_stab per Sec 2.4: within +-1% of the FINAL grade target, held 120s (24 scans) ----
    hold_scans = int(120 / DT_S)
    final_target = dst["target_bw"]
    within_band = (np.abs(100 * (basis_weight - final_target) / final_target) < 1.0)
    stable_idx = None
    if sheet_break_idx is None:
        ok = pd.Series(within_band).rolling(hold_scans).apply(lambda w: w.all()).fillna(False).astype(bool).values
        idxs = np.where(ok[RAMP_START_IDX:])[0]
        if len(idxs):
            stable_idx = RAMP_START_IDX + idxs[0] - hold_scans + 1
    t_stab_s = (stable_idx - RAMP_START_IDX) * DT_S if stable_idx is not None and stable_idx >= RAMP_START_IDX else None
    censored = t_stab_s is None

    # E-09: operator aborts/reverses mid-ramp. The physical trajectory up to that
    # point is real data; T_stab is meaningless for a transition that never
    # completed, so it's recorded as censored rather than attributed to model failure.
    reversed_event = (inject_fault is None) and (rng.random() < 0.04)
    if reversed_event:
        t_stab_s = None
        censored = True

    # Outcome follows directly from the two things that matter (Sec 1.3/2.4), not an
    # arbitrary extra time threshold: did it stabilize within the observation window,
    # and did it breach spec at any point while getting there.
    if sheet_break_idx is not None:
        outcome = "ABORTED"
    elif reversed_event:
        outcome = "REVERSED"
    elif censored:
        outcome = "FAILURE"
    elif sustained_off_spec.any():
        outcome = "DEGRADED"
    else:
        outcome = "SUCCESS"

    chained = (not reversed_event and sheet_break_idx is None and rng.random() < 0.10)
    confounded = (not reversed_event and sheet_break_idx is None and rng.random() < 0.05)

    frame = pd.DataFrame({
        "t_sec": t,
        "STOCK_FLOW": stock_flow, "STOCK_FLOW_SP": stock_flow_sp,
        "FILLER_FLOW": filler_flow, "FILLER_FLOW_SP": filler_flow_sp,
        "STEAM_PRESS_G1": steam_pressure,
        "MACHINE_SPEED": machine_speed, "MACHINE_SPEED_SP": machine_speed_sp,
        "BW_MEAS": basis_weight, "BW_SP": bw_sp,
        "MOIST_MEAS": moisture, "ASH_MEAS": ash, "CALIPER_MEAS": caliper,
        "HEADBOX_CONSISTENCY": consistency, "DRYER_HOOD_HUMID": dryer_hood_humid,
        "RETENTION_AID_FLOW": retention_aid_flow, "BROKE_RATIO": broke_ratio,
        "SCANNER_VALID": scanner_valid.astype(float), "SCANNER_STANDARDIZING": scanner_standardizing.astype(float),
        "SHEET_BREAK": sheet_break_flag.astype(float),
        "bw_deviation_pct": bw_dev_pct, "off_spec": off_spec, "sustained_off_spec": sustained_off_spec,
    })
    for tag, qarr in quality.items():
        frame[f"{tag}__quality"] = qarr

    meta = {
        "event_id": event_id, "from_grade": from_grade, "to_grade": to_grade,
        "final_target_bw": final_target, "t_stab_s": t_stab_s, "censored": censored,
        "outcome": outcome, "fault_injected": inject_fault, "chained": chained,
        "confounded": confounded, "theta_bw_s": theta_bw, "responsiveness": responsiveness,
    }
    return {"frame": frame, "meta": meta, "alarms": alarms}


def simulate_operator_actions(frame: pd.DataFrame, responsiveness: float, rng: np.random.Generator) -> list[dict]:
    """A MODELED operator decision process, not random noise: an operator
    watches |bw_deviation_pct|, and when it crosses a noticing threshold,
    reacts -- after a human reaction delay, not instantly -- by nudging
    whichever handle mass balance says is the primary BW lever (stock flow,
    proportional; machine speed, inverse), in the direction that corrects the
    deviation, sized roughly to the size of the miss. `responsiveness` (the
    same per-event execution-quality factor the physics itself uses) governs
    both how likely the operator is to notice/act and how precisely they
    execute the correction -- a more skilled operator reacts more often and
    more accurately, a less skilled one reacts less and overshoots more.
    A cooldown after each action stops the operator from re-triggering every
    single scan while waiting to see the effect of what they just did.

    Scope note: these actions are logged as realistic operator behaviour for
    the Event Timeline / underused-site-data story; they do NOT feed back
    into the simulated BW trajectory itself (`simulate_transition` has
    already run by the time this is called). Actually closing that loop
    would mean interleaving operator intervention into the FOPDT recursion
    mid-simulation -- a much larger change to logic that AC-1's calibrated
    metrics already depend on, and out of scope for this fix.
    """
    REACT_THRESHOLD_PCT = 1.2
    COOLDOWN_SCANS = 15  # ~75s: wait to see the effect before reacting again
    HANDLE_SCALE = {"STOCK_FLOW_SP": 1.0, "MACHINE_SPEED_SP": 9.0}  # proportional vs inverse lever, different units

    dev = frame["bw_deviation_pct"].values
    t_sec = frame["t_sec"].values
    n = len(frame)

    actions = []
    last_action_idx = -COOLDOWN_SCANS
    for i in range(n):
        if i - last_action_idx < COOLDOWN_SCANS or abs(dev[i]) < REACT_THRESHOLD_PCT:
            continue
        # Attentiveness: a more responsive/skilled operator is more likely to
        # catch and act on a given deviation.
        if rng.random() > min(0.9, 0.35 * responsiveness):
            continue

        reaction_delay = int(rng.integers(2, 5))  # ~10-20s human reaction time
        react_idx = min(i + reaction_delay, n - 1)
        if abs(dev[react_idx]) < 0.3:
            continue  # self-corrected before the operator got to it

        tag = "STOCK_FLOW_SP" if rng.random() < 0.65 else "MACHINE_SPEED_SP"
        sign = np.sign(dev[react_idx])
        # STOCK_FLOW_SP is proportional to BW: reduce it when BW is too high.
        # MACHINE_SPEED_SP is inverse to BW: raise it when BW is too high.
        correction_sign = -sign if tag == "STOCK_FLOW_SP" else sign
        magnitude = min(abs(dev[react_idx]) * 1.0, 3.0) * HANDLE_SCALE[tag]
        # Execution imprecision scales inversely with responsiveness -- a
        # less skilled operator both under/over-shoots more.
        imprecision = rng.uniform(1.0 - 0.25 / responsiveness, 1.0 + 0.25 / responsiveness)
        delta = correction_sign * magnitude * imprecision

        old_value = float(frame[tag].iloc[react_idx])
        actions.append({
            "t_sec": int(t_sec[react_idx]), "tag": tag,
            "old_value": round(old_value, 2), "new_value": round(old_value + delta, 2),
        })
        last_action_idx = react_idx

    return actions


def _melt_to_canonical(frame: pd.DataFrame, event_id: str, ts_start: pd.Timestamp, machine_id: str) -> pd.DataFrame:
    value_tags = ["STOCK_FLOW", "STOCK_FLOW_SP", "FILLER_FLOW", "FILLER_FLOW_SP", "STEAM_PRESS_G1",
                  "MACHINE_SPEED", "MACHINE_SPEED_SP", "BW_MEAS", "BW_SP", "MOIST_MEAS", "ASH_MEAS",
                  "CALIPER_MEAS", "HEADBOX_CONSISTENCY", "DRYER_HOOD_HUMID", "RETENTION_AID_FLOW",
                  "BROKE_RATIO", "SCANNER_VALID", "SCANNER_STANDARDIZING", "SHEET_BREAK"]
    units = {"STOCK_FLOW": "lpm", "STOCK_FLOW_SP": "lpm", "FILLER_FLOW": "lpm", "FILLER_FLOW_SP": "lpm",
             "STEAM_PRESS_G1": "kPa", "MACHINE_SPEED": "mpm", "MACHINE_SPEED_SP": "mpm",
             "BW_MEAS": "gsm", "BW_SP": "gsm", "MOIST_MEAS": "pct", "ASH_MEAS": "pct", "CALIPER_MEAS": "um",
             "HEADBOX_CONSISTENCY": "pct", "DRYER_HOOD_HUMID": "pct", "RETENTION_AID_FLOW": "lpm",
             "BROKE_RATIO": "pct", "SCANNER_VALID": "bool", "SCANNER_STANDARDIZING": "bool", "SHEET_BREAK": "bool"}
    rows = []
    for tag in value_tags:
        qcol = f"{tag}__quality"
        qual = frame[qcol] if qcol in frame.columns else "GOOD"
        rows.append(pd.DataFrame({
            "ts": ts_start + pd.to_timedelta(frame["t_sec"], unit="s"),
            "machine_id": machine_id,
            "tag": tag,
            "value": frame[tag].astype(float),
            "unit": units[tag],
            "quality": qual if isinstance(qual, str) else qual.values,
            "event_id": event_id,
        }))
    return pd.concat(rows, ignore_index=True)


def generate_dataset(n_transitions: int = 160, seed: int = 42, machine_id: str = "PM1") -> dict:
    rng = np.random.default_rng(seed)
    base_ts = pd.Timestamp("2026-01-05T06:00:00Z")

    all_long, all_events, all_alarms, all_actions = [], [], [], []
    fault_schedule = (
        [None] * int(n_transitions * 0.70)
        + list(np.repeat(FAULT_TYPES, max(1, int(n_transitions * 0.30 / len(FAULT_TYPES)))))
    )
    fault_schedule = fault_schedule[:n_transitions]
    rng.shuffle(fault_schedule)

    for i in range(n_transitions):
        from_g, to_g = rng.choice(GRADE_NAMES, 2, replace=False)
        event_id = f"EVT{i:04d}"
        ts_start = base_ts + pd.Timedelta(hours=int(rng.integers(4, 20)) + i * 9)  # monotonically increasing (NFR-M2)

        result = simulate_transition(event_id, from_g, to_g, rng, inject_fault=fault_schedule[i])
        frame, meta, alarms = result["frame"], result["meta"], result["alarms"]

        long_df = _melt_to_canonical(frame, event_id, ts_start, machine_id)
        all_long.append(long_df)

        all_events.append({
            "transition_id": event_id, "ts_start": ts_start,
            "ts_end": ts_start + pd.Timedelta(seconds=int(frame["t_sec"].max())),
            "machine_id": machine_id, "grade_from": from_g, "grade_to": to_g,
            "trigger": "AUTO", "outcome": meta["outcome"],
            "chained": meta["chained"], "confounded": meta["confounded"],
            "stabilization_time_sec": meta["t_stab_s"], "censored": meta["censored"],
            "fault_injected": meta["fault_injected"] or "", "theta_bw_s": meta["theta_bw_s"],
        })
        for a_ts, a_code in alarms:
            all_alarms.append({"event_id": event_id, "ts": ts_start + pd.Timedelta(seconds=int(a_ts)), "alarm": a_code})
        off_spec_rows = frame[frame["sustained_off_spec"]]
        for a_ts in off_spec_rows["t_sec"].iloc[::5]:
            all_alarms.append({"event_id": event_id, "ts": ts_start + pd.Timedelta(seconds=int(a_ts)),
                                "alarm": "BASIS_WEIGHT_OFF_SPEC"})

        # Modeled operator decision process (reacts to actual deviation, not
        # random timing/target) -- see simulate_operator_actions()'s docstring.
        # Uses its OWN independent, deterministic RNG stream (seeded from
        # [seed, i]) rather than drawing from the shared `rng` above: the
        # number of draws this makes varies with how often the deviation
        # actually crosses the react threshold, and consuming a variable
        # number of draws from the SHARED stream would shift every
        # subsequent event's grade-pair/fault/responsiveness draws too --
        # still deterministic given the same seed, just silently different
        # from a run before this feature existed, which is exactly what
        # happened to the AC-7 measurement the first time this was tried.
        action_rng = np.random.default_rng([seed, i])
        for act in simulate_operator_actions(frame, meta["responsiveness"], action_rng):
            all_actions.append({
                "ts": ts_start + pd.Timedelta(seconds=act["t_sec"]), "machine_id": machine_id,
                "operator_id": f"OP{int(action_rng.integers(1, 6)):02d}", "tag": act["tag"],
                "old_value": act["old_value"], "new_value": act["new_value"],
                "action_type": "SETPOINT_NUDGE", "free_text": "",
            })

    process_timeseries = pd.concat(all_long, ignore_index=True)
    grade_events = pd.DataFrame(all_events)
    alarm_history = pd.DataFrame(all_alarms) if all_alarms else pd.DataFrame(columns=["event_id", "ts", "alarm"])
    operator_actions = pd.DataFrame(all_actions)

    recipe_rows = []
    for gname, g in GRADES.items():
        specs = [
            ("BW_MEAS", g["target_bw"], 0.025, 0.04),
            ("MOIST_MEAS", g["target_moisture"], 0.15, 0.25),
            ("ASH_MEAS", g["target_ash"], 0.15, 0.25),
            ("CALIPER_MEAS", g["target_caliper"], 0.05, 0.08),
        ]
        for var, sp, spec_frac, alarm_frac in specs:
            recipe_rows.append({
                "grade_id": gname, "variable": var, "setpoint": sp,
                "lo_spec": sp * (1 - spec_frac), "hi_spec": sp * (1 + spec_frac),
                "lo_alarm": sp * (1 - alarm_frac), "hi_alarm": sp * (1 + alarm_frac),
                "ramp_rate_max": sp * 0.05, "source": "RECIPE",
            })
    recipe_limits = pd.DataFrame(recipe_rows)

    process_timeseries.to_parquet(OUT_DIR / "process_timeseries.parquet", index=False)
    grade_events.to_parquet(OUT_DIR / "grade_events.parquet", index=False)
    alarm_history.to_parquet(OUT_DIR / "alarm_history.parquet", index=False)
    operator_actions.to_parquet(OUT_DIR / "operator_actions.parquet", index=False)
    recipe_limits.to_parquet(OUT_DIR / "recipe_limits.parquet", index=False)
    # CSV mirrors for quick inspection / tools without parquet support
    for name, df in [("grade_events", grade_events), ("alarm_history", alarm_history),
                      ("operator_actions", operator_actions), ("recipe_limits", recipe_limits)]:
        df.to_csv(OUT_DIR / f"{name}.csv", index=False)

    print(f"[physics_simulator] {n_transitions} transitions, {len(process_timeseries)} canonical rows")
    print(f"  outcomes: {grade_events.outcome.value_counts().to_dict()}")
    print(f"  faults injected: {grade_events[grade_events.fault_injected != ''].fault_injected.value_counts().to_dict()}")
    return {"process_timeseries": process_timeseries, "grade_events": grade_events,
            "alarm_history": alarm_history, "operator_actions": operator_actions,
            "recipe_limits": recipe_limits}


if __name__ == "__main__":
    generate_dataset()
