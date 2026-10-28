# Item 1b battery-source qualification — 2026-10-27

**Decision: GO for longer-window whole-laptop battery-energy measurements using
`Windows.Devices.Power.BatteryReport`, read from WSL2 through Windows PowerShell.**
Austin authorized the unplugged check. This meets D12's 2026-11-01 source-selection
deadline. The source is a battery-controller estimate, without external-meter validation;
package energy and individual-inference energy remain unavailable.

## Run and preserved evidence

The team laptop ran Ubuntu 22.04.5 under WSL2. The check ran from
2026-10-28 02:16:08 to 02:20:39 UTC (October 27 locally): 120 seconds idle,
120 seconds with four CPU SHA-256 workers, and 30 seconds recovery. Polling was
requested every 10 seconds. Actual recording duration was 270.620 seconds.
All 28 native readings were valid, discharging, and AC disconnected.

| Observation | Result |
| --- | --- |
| Remaining energy, first → last | 31,874 → 28,785 mWh |
| Reported energy drop | 3.089 Wh = 11,120.4 J |
| Native full-charge capacity | 38,646 mWh |
| Distinct remaining-energy readings | 9 |
| Median observed energy step | 0.387 Wh |
| Observed update intervals | Approximately 30–40 seconds |
| Idle / load / recovery median reported power | 41.177 / 37.403 / 37.631 W |

The load phase reported less power than idle. Background activity and reporting lag
were not controlled sufficiently to explain this. This run qualifies the reporting
path; it establishes neither a CPU-load effect nor VLM-policy savings. The load workers
were stopped and recording completed successfully.

Evidence: [raw samples](examples/1b-battery-qualification/samples.jsonl),
[original manifest](examples/1b-battery-qualification/manifest.json),
[original decision](examples/1b-battery-qualification/qualification.json), and
[post-run granularity assessment](examples/1b-battery-qualification/assessment.json).
These are unchanged copies of local run outputs, except the explicitly separate
post-run assessment. The manifest hashes the executed qualification script; its exact
snapshot remains in the ignored original results directory. Subsequent source changes
add validation guards, run identity and assessment statistics and were checked with fakes;
they were not a second live battery run. The output directory's timestamp label is not
the authoritative start time; use the manifest timestamps.

## Selected source and rejected scale

WinRT explicitly reports remaining/full capacity in mWh and charge rate in mW.
Convert remaining capacity to joules with `mWh × 3.6`; energy used over a verified
discharge window is `(remaining_start − remaining_end) / 1000` Wh. Preserve negative
native charge rate during discharge; the reader exposes its negation in watts as
`discharge_power_w`. Require battery status `Discharging` and power-supply status
`NotPresent`. `Inadequate` still indicates external power and is rejected.
See Microsoft's [BatteryReport properties](https://learn.microsoft.com/en-us/uwp/api/windows.devices.power.batteryreport?view=winrt-26100)
and [PowerSupplyStatus values](https://learn.microsoft.com/en-us/uwp/api/windows.system.power.powersupplystatus?view=winrt-26100).

The WSL battery attributes changed while unplugged, but their full capacity was
5,000,000 uWh (5 Wh), versus Windows' 38.646 Wh. Their absolute scale is therefore
unqualified. Keep the existing `wsl_host_validation_required` flag; do not multiply
these values by an inferred correction factor. RAPL/powercap counters remain absent.

## Handoff to application and experiments

- Use `energy.windows.WindowsBatteryReader.read()` for qualified native readings.
  Windows PowerShell interop must be available as `powershell.exe`; no admin access
  or execution-policy changes are needed. Failures and unknown values remain missing.
- Retain query start, query availability, native UTC observation, AC/battery state,
  validity and raw capacities. API observation time does not establish when hardware
  last refreshed. Do not attribute one coarse energy step to a particular frame.
- The qualification script records both native JSONL readings and WSL diagnostics.
  It aborts on invalid readings, AC reconnection or charge below 20%, preserves partial
  output, and cleans up its CPU workers. It creates a new output directory each run.
- Shawn's 2f protocol should choose windows spanning many energy updates and sufficient
  energy change to resolve the expected difference. Match collection cadence and
  overhead between policies, record charge/power settings/background activity, and
  use repeated controlled trials. Final trials must recheck discharge throughout.
- Austin's 3a logic can use fixture costs; 3c must calibrate costs through batches or
  long runs in this same domain. The source includes Windows and all laptop activity.
  Item 2d still owns the shared evaluation schema and run integration.

A four-reading follow-up WMI probe showed finer capacity changes while WinRT remained
constant. That path did not receive this full qualification, and its unit-capability
metadata was not established. It is a follow-up candidate, not the selected source.

Results may vary depending on whose laptop runs the tests. This qualification applies
to the tested laptop; hardware, battery health, power settings and background activity
can change energy use, latency and sensor behavior. Record the laptop/configuration,
repeat source qualification for additional laptops, and keep policy comparisons on the
same machine. Report results from different laptops separately.

## Reproduction

With owner authorization and the laptop unplugged, from the repository root:

```bash
uv run python scripts/qualify_battery.py --output results/battery-qualification-new \
  --idle-seconds 120 --load-seconds 120 --recovery-seconds 30 --interval 10 --workers 4
```

This command deliberately runs a bounded CPU load. Automated tests use fakes and do
not require unplugging, a model or a live battery. The 76-test suite and Ruff checks
passed after the reader and qualification helper were added. GitHub issue closure and
merging remain separate from evidence completion.
