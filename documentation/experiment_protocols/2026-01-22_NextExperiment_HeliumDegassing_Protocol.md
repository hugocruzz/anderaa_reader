# Protocol — Helium degassing water tank (next experiment)

Date: 2026-01-22  
Project: Anderaa tank degassing tests  
Primary sensor: Anderaa 4330 (O2 saturation %)  
Log format: `Log/*.jsonl` produced by the reader

## 1) Goal and decision criteria

### 1.1 Goal
Determine the **optimal helium flow rate** to degas water in the tank, based on:
- **Degassing speed**: slope of O2 saturation vs time (more negative is faster).
- **Helium efficiency**: degassing speed per helium usage.

### 1.2 Metrics
- **Slope** $m$: O2 saturation change rate
  - Units: %/min
  - Computed by linear regression over a steady window.
- **Efficiency** $E$:
  - $E = -m / Q$ where $Q$ = helium flow (L/min)
  - Units: (%/min)/(L/min) = %/L

**Interpretation**
- If helium is limited/costly: choose **max $E$**.
- If time is critical: choose **most negative $m$**.

## 2) What we learned from Test 1 (why this protocol is stricter)

From Test 1:
- Changing **tank open/closed** strongly changes degassing (big confounder).
- Short intervals after changing flow can include transients.

Therefore, the protocol below:
- Changes **one factor at a time**.
- Adds **stabilization time** before fitting slopes.
- Uses **replicates** to measure variability.

## 3) Variables

### 3.1 Independent variables (what we intentionally change)
1) Helium flow rate $Q$ (L/min)
   - Suggested set: 0.25, 0.5, 1.0, 1.5, 2.0 L/min (adjust if your regulator is limited)
2) Tank state
   - Open vs closed (run as a separate experiment block)

### 3.2 Controlled variables (must stay constant)
- Water volume / water height (target: **290 mm**; record actual)
- Diffuser type and condition (same diffuser; record if changed)
- Diffuser depth (mm below surface)
- Helium inlet position (location in tank)
- Mixing method
  - Either: “no mixing” OR “fixed mixing protocol” (recommended)
  - If mixing: same stirring speed, same on/off schedule
- Temperature (record from sensor)
- Salinity/Conductivity (if relevant; record)

### 3.3 Measured variables (log)
- O2 saturation (%) from 4330
- Temperature (°C)
- (Optional) O2 concentration (µmol/L)
- Conductivity/Salinity (from 5819) for context

## 4) Equipment checklist

- Helium cylinder + regulator + calibrated flow meter (L/min)
- Tubing + fittings + diffuser
- Water tank (test tank) + pumping tank
- Sensors:
  - 4330 O2 sensor (must remain submerged during slope windows)
  - (Optional) 5819 conductivity, 4117 pressure/depth
- Laptop + Anderaa reader logging to `Log/`
- Timer/clock visible (use 24h time)

## 5) Pre-flight checks (before recording)

1) **Sensor stabilization**
   - Put sensors in water, wait 5–10 min until readings are stable.
2) **Confirm logging**
   - Start the reader and confirm new JSONL log is being written.
3) **Flow meter sanity**
   - Verify helium flow setpoint is stable and repeatable.
4) **Leak check**
   - Check tubing connections for leaks.

## 6) Experimental design (recommended)

Run two separate blocks on the same day if possible:

### Block A — Tank OPEN (baseline)
Purpose: isolate effect of flow rate without headspace sealing effects.

### Block B — Tank CLOSED
Purpose: quantify effect of sealing and interaction with flow.

Within each block:
- Test multiple flow rates in randomized order.
- Repeat at least **2 replicates** per flow if time allows.

**Why randomize order?**
To reduce bias from time/temperature drift.

## 7) Step-by-step procedure (per block)

### 7.1 Start of block
1) Set tank state (OPEN or CLOSED) and keep it unchanged for the whole block.
2) Fill tank to target height (record mm).
3) Place diffuser at the chosen depth (record mm).
4) Place sensors at fixed position (record depth and location).
5) Start logging and write down:
   - Log filename
   - Start time
   - Block type (OPEN/CLOSED)

### 7.2 For each flow rate step
For each flow $Q$ in your schedule:

1) Set helium flow to $Q$.
2) **Event note**: record exact time and flow in the notes.
3) **Stabilization period**: wait **2 minutes** (no slope calculation during this time).
4) **Measurement window**: record at constant conditions for **6 minutes**.
   - Keep mixing constant (either always on or always off as defined).
   - Do not move sensors.
5) (Optional) **Mixing test**: if you want to test mixing as a factor, do it in a separate block, not here.

**Minimum time per flow step**: 8 minutes (2 min stabilize + 6 min measure).

### 7.3 End of block
- Stop helium.
- Keep logging for 2–3 min to capture recovery if desired.
- Stop recording.

## 8) Flow schedule template

Choose one schedule depending on time:

### Short schedule (~40–50 min per block)
- 0.5 → 1.0 → 2.0 → 1.5 → 0.25 (randomized example)

### Detailed schedule (~70–90 min per block)
- 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0 (random order)

## 9) Notes template (copy/paste during run)

Block: OPEN or CLOSED  
Tank height: ____ mm  
Diffuser: type ____ ; depth ____ mm  
Mixing: OFF / ON (speed ____ )  
Log file: Log/________________.jsonl  

Timeline:
- HH:MM:SS — Start logging
- HH:MM:SS — Set helium to Q=___ L/min
- HH:MM:SS — (after 2 min stabilization) start slope window for Q=___
- HH:MM:SS — End slope window for Q=___
(repeat)

## 10) Data analysis workflow

### 10.1 Plot and annotate
Use the existing script:
- Run: `C:/Users/cruz/AppData/Local/anaconda3/envs/pylake/python.exe src/analysis/plot_o2_experiment.py --log Log/<yourlog>.jsonl --no-show`
- Output PNG goes to: `documentation/experiment_notes/plots/`

### 10.2 Slope calculation rules
For each flow step:
- Ignore first **2 minutes** after changing flow.
- Fit slope on the next **6 minutes**.
- Report: slope (%/min), R², number of points.

### 10.3 Compare flows
For each flow $Q$:
- Average slope across replicates.
- Compute efficiency $E=-m/Q$.
- Rank flows by:
  - fastest degassing (most negative slope)
  - best efficiency (largest %/L)

## 11) Practical recommendations to reduce uncertainty

- Keep sensor submerged the entire time; define a “valid data” interval.
- Avoid changing tank state mid-run.
- If you must replace diffuser, stop and start a **new block**.
- If bubble pattern changes drastically, note it (bubble size affects mass transfer).

## 12) Acceptance criteria (what “good data” looks like)

- Each flow step has ≥ 6 min stable window.
- Linear fit R² is reasonably high (rule of thumb: R² ≥ 0.9).
- Replicates at the same flow produce similar slopes.

## 13) Safety

- Secure helium cylinder and avoid tipping.
- Ensure ventilation (helium can displace oxygen in enclosed spaces).
- Avoid over-pressurizing any sealed tank (if closing tank, confirm safe venting design).
