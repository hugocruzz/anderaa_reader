
# Enclosure Test Protocols — Subocean + Aanderaa Sensors

Date started: 2026-01-05  
Owner: (fill)  
System: Water-filled pressure enclosure used to test Subocean (membrane inlet mass spectrometer) under controlled $P$, $T$, and dissolved gas conditions.

## 1) Purpose and scope

This document defines the **methodology**, **good practices**, and **step-by-step protocols** for enclosure tests where:

- The enclosure is filled with water.
- A membrane-based instrument (Subocean) measures dissolved gases in the enclosure water.
- External control variables include pressure, temperature, and gas composition.
- Independent monitoring uses Aanderaa sensors:
  - Pressure (4117B)
  - Oxygen optode (4330IW)
  - (Optional) Conductivity/temperature (5819C)

Primary goals (current phase):

1. Estimate **time and helium flow** needed to degas the **pump/line water volume** (pre-degassing step).
2. Estimate **time and helium flow** needed to degas the **enclosure tank water volume**.
3. Run “gas dose → close tank → pressurize” experiments (details pending) while ensuring correct **valve closure sequencing**.

## 2) Definitions (keep consistent across notes)

- **Enclosure / tank**: the pressure vessel holding water and Subocean membrane.
- **Pump loop**: pump + tubing + any reservoir used to deliver water and pressurize the enclosure.
- **Degassing**: stripping dissolved gases using helium sparging (or helium bubbling through a tube) controlled by an MFC (Bronkhorst).
- **“Degassed water”**: water that has undergone a defined degassing procedure (document the procedure each time).

## 3) Safety and constraints (minimum)

This setup includes pressure and compressed gas hazards.

- Only operate within the enclosure’s rated pressure and temperature limits.
- Use a pressure relief strategy (rated relief valve or equivalent), and never defeat it.
- Verify all wetted components are rated for max pressure.
- Verify helium supply, regulators, and MFC limits before opening cylinder.
- Treat oxygen readings as *process indicators*, not safety-certified measurements.

## 4) Hardware and instrumentation checklist

### 4.1 Equipment list (fill in specifics)

- Enclosure / tank: model, internal volume $V_{tank}$ = (fill) L
- Subocean: firmware version = (fill)
- Aanderaa pressure sensor 4117B: SN 2378
- Aanderaa oxygen optode 4330IW: SN 4445
- Aanderaa conductivity sensor 5819C: SN 385 (optional)
- Helium source + regulator
- MFC (Bronkhorst): model, range, calibration gas (He) = (fill)
- Pump: model, max pressure, flow range
- Tubing: material, ID/OD, total length (approx)
- Valves: list V1..Vn (see §4.2)
- Temperature control (if any): chiller/heater, setpoint control

### 4.2 Valve map (required for repeatability)

Create a simple valve naming convention and keep it stable.

Fill this table once and reuse it:

| Valve ID | Physical location | Function | Normal state | Notes |
|---|---|---|---|---|
| V1 | (fill) | He injection to (pump/tank) | Closed | |
| V2 | (fill) | Vent / headspace | Closed | |
| V3 | (fill) | Pump inlet | Closed | |
| V4 | (fill) | Pump outlet to tank | Closed | |
| V5 | (fill) | Drain | Closed | |

If you already have a drawing/photo, link it here: (path/URL).

## 5) Data logging and traceability (good practice)

### 5.1 Time sync

- Set the logging computer time correctly before each run.
- Record local timezone and whether timestamps are UTC.

### 5.2 What to log (minimum)

For every run, log:

- He MFC setpoint (sccm or slpm) and actual flow (if available)
- Pump setpoint(s): pressure, flow, duty cycle
- Tank pressure (Aanderaa 4117B)
- Water temperature(s): from 4330/5819 and/or external probe
- O2 (4330IW): concentration and saturation (use one consistently; recommend concentration)
- Subocean outputs: gas channels, raw signals, and any internal temperature/pressure if provided

### 5.3 File naming convention (recommended)

Use a run ID that sorts chronologically:

`YYYYMMDD_runNN_<phase>_<shortdesc>`

Examples:

- `20260105_run01_pump-degas_helium-100sccm`
- `20260105_run02_tank-degas_helium-200sccm`

### 5.4 Run log (fill during experiments)

Use the template in §10 for each run.

## 6) General operating methodology

These rules avoid ambiguity and make later analysis possible.

### 6.1 Stabilize one variable at a time

- For degassing characterization, keep pressure and temperature as stable as possible.
- When changing pressure, document the change rate (e.g., “+1 bar/min”).

### 6.2 Define “done” using objective criteria

For degassing, choose criteria before starting, e.g.:

- O2 concentration $<$ threshold (e.g., < 5 µM) **OR**
- |d(O2)/dt| < slope threshold (e.g., < 0.2 µM/min) for 10 min

Pick values appropriate to your baseline and sensor noise; keep them consistent across runs.

### 6.3 Control artifacts

- Avoid bubbles on sensors and membrane (tap/tilt protocol, slow flows).
- Avoid long periods of stagnant water if stratification is expected.
- Record if the tank was opened to atmosphere at any point.

## 7) Pre-run checks (always do)

1. **Leak/pressure integrity**
	- Verify all fittings tight.
	- Confirm pressure sensor reading is plausible at ambient.
2. **Sensor health**
	- Connect Aanderaa sensors and verify live readings.
	- Record sensor serial numbers and any calibration notes.
3. **Baseline water state**
	- Record initial temperature, pressure, and O2.
4. **Subocean readiness**
	- Confirm membrane installed and wetted per Subocean procedure.
	- Confirm Subocean logging starts before any gas manipulation.
5. **MFC check**
	- Confirm helium cylinder pressure, regulator outlet pressure.
	- Confirm MFC setpoint units and range.

## 8) Protocol A — Degas characterization of pump/line water (Goal 1)

### 8.1 Objective

Estimate helium flow and time required to reach a defined degassing endpoint for the **pump/line water volume**.

### 8.2 Controls and assumptions

- Keep tank isolated or bypassed so the experiment targets the pump loop.
- Keep temperature constant (or record if it drifts).
- Define an endpoint criterion (see §6.2).

### 8.3 Procedure (suggested step-by-step)

1. Configure the plumbing so helium contacts the pump-loop water volume (document which valves open/closed).
2. Fill the pump loop with water (no visible trapped gas pockets if possible).
3. Start Aanderaa logging (pressure, O2, temperature).
4. Start Subocean logging (even if not the primary metric).
5. Set pump operation mode (circulation/recirculation). Record settings.
6. Start helium degassing:
	- Set MFC to the planned flow (e.g., 50, 100, 200 sccm).
	- Record start time.
7. Monitor O2 response:
	- Continue until endpoint criterion is reached.
	- Record any adjustments (flow changes, pump changes).
8. Stop helium flow, continue logging for 10–20 min to observe rebound.

### 8.4 What to record (minimum)

- Estimated pump-loop water volume $V_{loop}$ (best estimate; later refine)
- Helium flow (setpoint + actual)
- Pump state (on/off, speed)
- O2 vs time, temperature vs time
- Notes on bubbling quality (fine bubbles vs large bubbles), and bubble carryover

### 8.5 Analysis method (simple and repeatable)

Use O2 concentration time series $C(t)$.

- Define $C_0$ at helium start.
- Define $C_{end}$ at endpoint.
- Report time-to-endpoint $t_{end}$.

Optional (useful): fit an exponential decay $C(t) = C_{\infty} + (C_0 - C_{\infty})e^{-t/\tau}$ over the main decay region to estimate a time constant $\tau$. This helps compare runs with different starting conditions.

## 9) Protocol B — Degas characterization of enclosure tank water (Goal 2)

### 9.1 Objective

Estimate helium flow and time required to degas the **tank water volume**, as indicated by the O2 optode (and optionally Subocean signals).

### 9.2 Controls and assumptions

- Tank mixing strongly affects degassing time. Document mixing method:
  - Pump recirculation path
  - Internal stirrer (if any)
  - Bubble injection location and diffuser type

### 9.3 Procedure

1. Fill the tank with water to defined volume $V_{tank}$.
2. Ensure Subocean membrane is installed and submerged as intended.
3. Place/verify Aanderaa O2 sensor location (avoid direct bubble stream if possible).
4. Start logging (Aanderaa + Subocean).
5. Start mixing/recirculation (if used). Record settings.
6. Start helium degassing via MFC at planned setpoint. Record start time.
7. Continue until endpoint criterion reached (see §6.2).
8. Stop helium. Keep mixing and logging for 10–20 min.

### 9.4 Notes and decision points

- If O2 drops quickly then plateaus above endpoint, check for:
  - insufficient mixing
  - leaks / air ingress
  - trapped gas pockets
  - sensor bubble interference

## 10) Protocol C — Gas dose → close tank → pressurize (Goal 3, draft)

### 10.1 Objective

Introduce a known gas condition, close the tank, then increase pressure using degassed water via pump, while controlling valve states to prevent unwanted exchange.

### 10.2 Status

This protocol is a **draft** pending your detailed step notes (valve sequence, where gas is introduced, and which volumes are isolated).

### 10.3 Required inputs from you (to finalize)

Answering these will let me lock the valve-by-valve sequence:

1. Where is the “some gas” introduced (headspace, dissolved injection, inline)?
2. Do you have headspace in the tank during this step? (Yes/No)
3. Which valves must be closed before pressurizing? (Map to V1..Vn)
4. What is the pressurization method (pump adds degassed water, or gas pressure)?
5. Target pressure profile (step vs ramp) and max pressure.

### 10.4 Draft procedure skeleton

1. Initial state: tank filled, instruments logging, stable baseline.
2. Gas dose step:
	- Introduce gas per defined method.
	- Wait/mix for a defined equilibration time.
3. Isolation step:
	- Close the required valves (list exact V1..Vn).
	- Confirm closed-state by observing pressure stability (no drift) and no flow.
4. Pressurization step:
	- Increase pressure using degassed water via pump.
	- Record pressure vs time profile and pump settings.
5. Hold step:
	- Hold at target pressure for defined duration.
6. Depressurize step:
	- Controlled depressurization; record rate.

## 11) Quality checks and acceptance criteria (recommended)

### 11.1 Minimum acceptance for “usable run”

- Continuous time series with no major gaps for: pressure, temperature, O2, Subocean.
- Known start/stop times for helium flow and pressure changes.
- Valve configuration recorded.

### 11.2 Common failure modes (track them)

- O2 sensor reading biased by bubbles.
- Gas ingress through fittings (slow O2 rebound).
- Pressure sensor offset after cycling.
- Temperature drift causing apparent gas changes.

## 12) Run log template (copy/paste per run)

### Run ID

Run ID:  
Date/time start:  
Operator:  
Goal: (A pump-degas / B tank-degas / C gas-dose+pressurize)  

### Setup

- Water source: (tap / DI / seawater / other)  
- Water volume: $V_{tank}$ = ___ L, $V_{loop}$ = ___ L (estimate)  
- Temperature control: (none / chiller / heater) setpoint ___ °C  
- Subocean membrane: (type, install notes)  

### Instrumentation

- Pressure sensor 4117B: COM port ___  
- O2 optode 4330IW: COM port ___  
- Conductivity 5819C (optional): COM port ___  
- Subocean logging file(s): (path)  
- Aanderaa logging file(s): (path)  

### Valve state record (before run)

- V1: Open/Closed  
- V2: Open/Closed  
- V3: Open/Closed  
- V4: Open/Closed  
- V5: Open/Closed  

### Degassing / pressurization settings

- Helium MFC setpoint: ___ (units)  
- Helium start time: ___  
- Helium stop time: ___  
- Pump settings: (mode/speed/flow)  
- Pressure profile: (target, ramp rate)  

### Endpoint criterion

- Criterion used: (threshold / slope / both)  
- Threshold value(s):  
- Time reached:  

### Observations

- Visual bubble behavior:  
- Leaks / unusual sounds:  
- Sensor artifacts or dropouts:  

### Results summary (quick)

- Initial O2: ___  
- Final O2 at endpoint: ___  
- Time-to-endpoint: ___  
- Temperature range during run: ___–___ °C  
- Pressure range during run: ___–___  

---

## 13) Change log

- 2026-01-05: Initial protocol drafted.

