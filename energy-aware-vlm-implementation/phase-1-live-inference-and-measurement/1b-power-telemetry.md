# 1b — Power and energy telemetry

**Live issue:** [#2](https://github.com/austincbaker/cap6411-cv-systems/issues/2)
**Priority:** P0 (`priority:P0`)
**GitHub blocked by:** None

**Phase**: 1 — Establish live inference and measurement
**Status**: ⬜ Not started
**Plan refs**: [Master plan](../plan.md#phase-1--establish-live-inference-and-measurement-week-1); D08, D11; R03, R08
**Depends on**: None; independent Phase 1 discovery/build item
**Blocks**: [1d](../phase-1-live-inference-and-measurement/1d-fixed-interval-application.md), [2d](../phase-2-gated-application-and-contracts/2d-evaluation-contracts-and-fixtures.md), [3a](../phase-3-budget-control-and-evaluation-tools/3a-energy-budget-controller.md)

## Scope

Owner: Austin, with Shawn reviewing measurement validity. Capture timestamped power or cumulative-energy samples from the selected primary laptop. Document the sensor's domain, units and gaps so later results do not confuse CPU energy with battery energy.

## Tasks

- [ ] Select and verify the primary hardware/sensor path and record units, energy domains and available battery measurements.
- [ ] Implement sample collection with timestamps, validity and lifecycle cleanup.
- [ ] Provide a short trace and document missing samples and counter behavior for Shawn.

## Files to be touched

- `src/energy/monitor.py` — Proposed telemetry adapter.
- `docs/methodology.md` — Sensor limitations and units, coordinated with Shawn.

## Source references (if porting)

Not a port. The existing repository contains a placeholder `README.md` and a Python-oriented `.gitignore`; all implementation paths above are proposed. Use the master plan's supplied research references where relevant and verify technical claims during implementation.

## Open questions

- [ ] Verify the actual sensor permissions, availability and domain on the selected primary laptop before final trials.

## Acceptance criteria

- [ ] A short run records a declared power/energy domain and units.
- [ ] Unsupported sensors or gaps are recorded as unavailable instead of zero consumption.

## Definition of Done

The stub is considered complete when every row below shows 🟢.

| # | Task summary | Where in file | Done when | Implemented at | Status |
|---|---|---|---|---|---|
| 1 | Select and verify the primary hardware/sensor path and record units, energy domains and available battery measurements. | [Tasks](#tasks) | The chosen sensor returns interpretable samples, or an unavailable sensor is explicitly reported. | — | ⬜ |
| 2 | Implement sample collection with timestamps, validity and lifecycle cleanup. | [Tasks](#tasks) | A finite run produces a trace aligned with its measured start/end interval. | — | ⬜ |
| 3 | Provide a short trace and document missing samples and counter behavior for Shawn. | [Tasks](#tasks) | Shawn can explain the energy domain and calculate a check value from the trace. | — | ⬜ |
| 4 | All acceptance criteria met | [Acceptance criteria](#acceptance-criteria) | All checkboxes ticked | — | ⬜ |

## Implementation notes

### Context and boundaries

Austin owns collection; Shawn reviews measurement validity. Apply D08 (declared energy domains and total/incremental separation), D11 (Ubuntu 22.04.5 LTS), R03 (hardware support) and R08 (measurement noise). No sensor adapter exists in the repository. The laptop's CPU vendor, kernel, accessible energy counters and battery properties have not been verified.

Ubuntu selection authorizes a Linux implementation path; it does not establish that RAPL or battery telemetry is present. This item collects evidence and a usable trace. The final analysis and energy controller remain Shawn's item 3g and Austin's item 3a.

### Ordered implementation breakdown

1. Inspect the actual primary laptop's CPU, kernel, power supplies and readable sensor interfaces. Record these facts with the OS release and power mode; do not infer them from the development host.
2. Inventory available powercap energy zones and battery/AC attributes, recording the discovered path, descriptive name, measurement domain, units, permissions and supported properties. Unsupported hardware is a result of this check, not a zero reading.
3. If a powercap energy counter is available, select a clearly identified domain and retain its counter range. Avoid adding a package counter to its contained subdomains. The kernel documents cumulative `energy_uj` and `max_energy_range_uj` attributes. [Powercap reference](https://docs.kernel.org/power/powercap/powercap.html).
4. If battery telemetry is available, identify its actual properties and charging/discharging state before using it. Battery charge and stored energy are different quantities; use only documented unit conversions and do not treat charge capacity as energy. Driver-provided attributes can be absent. [Power-supply reference](https://docs.kernel.org/power/power_supply_class.html).
5. Define a narrow proposed collection interface in `src/energy/monitor.py` that reports sensor metadata and yields timestamped readings until stopped. Keep raw observation collection independent of VLM and analysis code.
6. Preserve the original reading/unit and a documented normalized value when conversion is valid. Record whether the sample is power or cumulative energy, its domain, elapsed monotonic time, validity and reason for missing data.
7. Use a configurable sampling interval and record actual sample times, not just the requested rate. Select the rate after observing sensor update frequency and collector overhead; oversampling a slowly updated battery value does not create new information.
8. Handle permission errors, malformed reads, disappearing devices and unavailable attributes explicitly. Continue unaffected sensors when possible; never carry forward an old reading as a new valid observation without marking that fact.
9. Preserve enough metadata to interpret a counter rollover, reset or suspend/resume discontinuity later. A wrapped delta is valid only when supported by the recorded range and sampling interval; do not silently assume every negative jump is a single wrap.
10. Start and stop collection around a documented measured interval, retaining partial traces on interruption and finalizing output cleanly. Collection must not change hardware power limits or tuning settings as a side effect.
11. Produce a short idle trace and a short local-load trace on the primary laptop, keeping them in the same sensor domain and power state. Ask Shawn to check elapsed time, units and basic variation against the raw values.
12. Add the hardware/sensor findings to the sensor section of `docs/methodology.md`, coordinating edits with Shawn's item 1f. State which measurements are possible and which are missing; give item 1d an explicit unavailable status when collection cannot proceed.

### Sample contract and measurement boundaries

For each observation, retain run/sensor/domain identity, elapsed time, raw quantity and unit, normalized value if available, and validity/error information. Include the counter range in sensor metadata when applicable. Final CSV column names and null encoding belong to item 2d; provide a small understandable sample now.

Keep battery/whole-laptop observations separate from CPU/package observations. Later subtraction against an idle baseline must use the same hardware, domain, units and interval basis. A package estimate is not a process-specific bill for a single inference.

Use these transparent check calculations when validating units: constant 10 W over 60 s corresponds to 600 J, or about 0.1667 Wh; its hourly normalized rate is 10 Wh/hour. The examples are arithmetic fixtures, not measured laptop results.

### Verification and acceptance interpretation

Proposed `tests/test_energy_monitor.py` should use temporary fake sensor files/readers and a controlled clock to check unit conversion, missing permissions/files, malformed readings, recorded counter ranges and stop/cleanup behavior. Check that missing samples cannot become valid zeros. Numerical integration/rollover policy tests remain in Shawn's `tests/test_energy_analysis.py` later; this item's collector must preserve the evidence they need.

A readable trace on the actual Ubuntu laptop establishes the positive collection criterion. If no suitable sensor can be read, document the limitation and notify the team before energy experiments; simulated traces can unblock consumer development but cannot satisfy a claim of measured energy. A budget controller must not claim live adherence while its accounting input is unavailable.

### Files and evidence recap

- `src/energy/monitor.py` — proposed hardware inventory/reading boundary, timestamped collection and shutdown.
- `docs/methodology.md` — sensor names/domains, units, coverage, selected cadence and limitations; Shawn owns the surrounding protocol.
- `tests/test_energy_monitor.py` — proposed fake-sensor checks; no privileged hardware or live battery required in automated tests.

The original open check remains pending until hardware is inspected. Sensor choice is evidence-led within the existing plan; do not add macOS/Windows backends or unrequested monitoring infrastructure.
