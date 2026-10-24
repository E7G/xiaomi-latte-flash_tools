# r5 normal 1080p encoded recording: cadence FAILED

Later full-quality foreground Snapshot tests completed and decoded, but front
29.351702 fps/26 gaps >50 ms and rear 29.766275 fps/12 gaps >50 ms both fail.
No threshold relaxation, hidden preview, lower bitrate/resolution or synthetic
frame duplication. Earlier native960/electrical/2RTC pass does not qualify
encoded app performance. Raw failed clips stay tablet-private; root cause
unestablished, not a controlled r4/r5 kernel A/B, no fix or OEM parity claimed.
Original settings/geometry/controls restored, apps terminal, sensors/ISP asleep;
2214 protected files +48 payload hashes +35 private aliases unchanged/fault0.

[Pinned failure evidence, comparison and limits](https://github.com/E7G/linux_latte/blob/bebc835f10a60a1e373d68311b21981a77d5f01a/fix_file/MIPAD2_R5_RECORDING_REGRESSION_7_2.md).
