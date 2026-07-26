"""
data_simulator.py
Generates realistic synthetic historical data for paper-machine grade changes.

Simulates:
- Multiple grade transitions (recipe A -> B) over time
- Core loop variables: stock_flow, filler_flow, steam_pressure, machine_speed
- Quality variables: basis_weight, moisture, ash, caliper
- A "hidden" correlation: ambient_humidity affects moisture stabilization speed,
  which in turn affects basis_weight overshoot -- NOT in the "known" loop list,
  so a good solution should surface this as a "new correlation".
- Mix of SUCCESS and FAILURE (off-spec) grade change events for the model to learn from.
- Operator actions log + alarm log, per the problem statement's "underused site data".
"""

import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(42)

OUT_DIR = Path(__file__).parent.parent / "data"
OUT_DIR.mkdir(exist_ok=True)

GRADES = {
    "GradeA": {"target_bw": 80, "target_moisture": 6.0, "target_ash": 12.0, "target_caliper": 120},
    "GradeB": {"target_bw": 95, "target_moisture": 6.5, "target_ash": 15.0, "target_caliper": 140},
    "GradeC": {"target_bw": 70, "target_moisture": 5.5, "target_ash": 10.0, "target_caliper": 100},
    "GradeD": {"target_bw": 110, "target_moisture": 7.0, "target_ash": 18.0, "target_caliper": 160},
}
GRADE_NAMES = list(GRADES.keys())

N_TRANSITIONS = 140          # number of historical grade-change events
WINDOW_MIN = 30               # minutes captured per transition (pre + during + post)
SAMPLE_RATE_SEC = 15          # one sample every 15s -> 120 samples per 30 min


def simulate_transition(event_id, from_grade, to_grade, ambient_humidity, operator_skill):
    """Simulate one grade-change event and return a DataFrame of time-series samples."""
    n = int(WINDOW_MIN * 60 / SAMPLE_RATE_SEC)
    t = np.arange(n) * SAMPLE_RATE_SEC

    src, dst = GRADES[from_grade], GRADES[to_grade]

    # Ramp starts at sample 20 (5 min baseline), completes by sample ~80 (20 min in)
    ramp_start, ramp_end = 20, 80
    progress = np.clip((np.arange(n) - ramp_start) / (ramp_end - ramp_start), 0, 1)

    # --- Core control loops (the ones the existing QCS already manages) ---
    stock_flow = 100 + (dst["target_bw"] - src["target_bw"]) * 0.8 * progress + np.random.normal(0, 0.6, n)
    filler_flow = 20 + (dst["target_ash"] - src["target_ash"]) * 1.1 * progress + np.random.normal(0, 0.3, n)
    steam_pressure = 40 + (dst["target_moisture"] - src["target_moisture"]) * 3.0 * progress + np.random.normal(0, 0.4, n)
    machine_speed = 900 - (dst["target_bw"] - src["target_bw"]) * 1.5 * progress + np.random.normal(0, 3, n)

    # --- Hidden/uncontrolled factor: ambient humidity affects how fast moisture (and
    #     therefore basis weight) actually stabilizes -- this is the "new correlation"
    #     the hackathon explicitly asks teams to discover. ---
    humidity_drag = (ambient_humidity - 45) / 100.0   # +ve => slower stabilization

    # Operator skill affects how well they fine-tune around the automatic ramp
    skill_noise = np.random.normal(0, max(0.8 * (1.2 - operator_skill), 0.05), n)

    # --- Quality variables (lagged response to the loops above + hidden humidity drag) ---
    # Basis weight overshoots/undershoots then decays back toward target, slower with humidity drag
    decay_rate = 0.06 * (1 - 0.5 * humidity_drag) * operator_skill
    decay_rate = max(decay_rate, 0.015)
    overshoot = (dst["target_bw"] - src["target_bw"]) * 0.25 * (1 + humidity_drag)
    bw_trend = dst["target_bw"] + overshoot * np.exp(-decay_rate * np.clip(np.arange(n) - ramp_start, 0, None)) * (progress > 0)
    basis_weight = np.where(progress < 0.02, src["target_bw"], bw_trend) + np.random.normal(0, 0.5, n) + skill_noise * 0.3

    moisture = dst["target_moisture"] + (0.4 + humidity_drag * 0.6) * np.exp(-0.05 * np.clip(np.arange(n) - ramp_start, 0, None)) * (progress > 0)
    moisture = np.where(progress < 0.02, src["target_moisture"], moisture) + np.random.normal(0, 0.08, n)

    ash = dst["target_ash"] + 0.3 * np.exp(-0.08 * np.clip(np.arange(n) - ramp_start, 0, None)) * (progress > 0)
    ash = np.where(progress < 0.02, src["target_ash"], ash) + np.random.normal(0, 0.15, n)

    caliper = dst["target_caliper"] + 2.0 * np.exp(-0.05 * np.clip(np.arange(n) - ramp_start, 0, None)) * (progress > 0)
    caliper = np.where(progress < 0.02, src["target_caliper"], caliper) + np.random.normal(0, 1.0, n)

    df = pd.DataFrame({
        "event_id": event_id,
        "t_sec": t,
        "from_grade": from_grade,
        "to_grade": to_grade,
        "ambient_humidity": ambient_humidity,
        "operator_skill": operator_skill,
        "stock_flow": stock_flow,
        "filler_flow": filler_flow,
        "steam_pressure": steam_pressure,
        "machine_speed": machine_speed,
        "basis_weight": basis_weight,
        "moisture": moisture,
        "ash": ash,
        "caliper": caliper,
        "target_basis_weight": dst["target_bw"],
    })

    df["bw_deviation_pct"] = 100 * (df["basis_weight"] - df["target_basis_weight"]) / df["target_basis_weight"]
    df["off_spec"] = df["bw_deviation_pct"].abs() > 2.5

    # Stabilization time: first time after ramp_start where |deviation| stays < 2.5% for 8 consecutive samples
    stable_idx = None
    ok = (df["bw_deviation_pct"].abs() < 2.5).values
    for i in range(ramp_start, n - 8):
        if ok[i:i + 8].all():
            stable_idx = i
            break
    df["stabilization_time_sec"] = (stable_idx - ramp_start) * SAMPLE_RATE_SEC if stable_idx else np.nan
    df["event_outcome"] = "SUCCESS" if (stable_idx is not None and (stable_idx - ramp_start) * SAMPLE_RATE_SEC < 600) else "FAILURE"

    return df


def simulate_operator_actions(transition_df, event_id):
    """A few discrete operator setpoint nudges during the transition (site data: operator actions)."""
    n_actions = np.random.randint(1, 4)
    rows = []
    for _ in range(n_actions):
        t = np.random.randint(20, 100) * SAMPLE_RATE_SEC
        loop = np.random.choice(["stock_flow", "steam_pressure", "filler_flow", "machine_speed"])
        delta = np.random.normal(0, 1.5)
        rows.append({"event_id": event_id, "t_sec": t, "loop": loop, "delta": round(delta, 2)})
    return pd.DataFrame(rows)


def main():
    all_ts, all_actions, all_alarms = [], [], []
    for i in range(N_TRANSITIONS):
        from_g, to_g = np.random.choice(GRADE_NAMES, 2, replace=False)
        ambient_humidity = np.random.uniform(25, 75)
        operator_skill = np.random.uniform(0.5, 1.3)  # 1.0 = average

        df = simulate_transition(f"EVT{i:04d}", from_g, to_g, ambient_humidity, operator_skill)
        all_ts.append(df)
        all_actions.append(simulate_operator_actions(df, f"EVT{i:04d}"))

        if df["off_spec"].any():
            alarm_rows = df[df["off_spec"]].iloc[::5][["event_id", "t_sec"]].copy()
            alarm_rows["alarm"] = "BASIS_WEIGHT_OFF_SPEC"
            all_alarms.append(alarm_rows)

    ts = pd.concat(all_ts, ignore_index=True)
    actions = pd.concat(all_actions, ignore_index=True)
    alarms = pd.concat(all_alarms, ignore_index=True) if all_alarms else pd.DataFrame(columns=["event_id", "t_sec", "alarm"])

    events = ts.drop_duplicates("event_id")[[
        "event_id", "from_grade", "to_grade", "ambient_humidity", "operator_skill",
        "stabilization_time_sec", "event_outcome"
    ]].reset_index(drop=True)

    ts.to_csv(OUT_DIR / "historian_timeseries.csv", index=False)
    actions.to_csv(OUT_DIR / "operator_actions.csv", index=False)
    alarms.to_csv(OUT_DIR / "alarm_history.csv", index=False)
    events.to_csv(OUT_DIR / "events_summary.csv", index=False)

    print(f"Generated {N_TRANSITIONS} grade-change events, {len(ts)} time-series rows.")
    print(f"Success: {(events.event_outcome == 'SUCCESS').sum()}  |  Failure: {(events.event_outcome == 'FAILURE').sum()}")
    print(f"Files written to: {OUT_DIR}")


if __name__ == "__main__":
    main()
