# 7.2 native capture scheduling candidate: NOT stable qualification

## Stop condition: subsequent device freeze

After both short tests had exited normally and both sensors/ISP reported runtime
suspended, a fresh whole-device postflight could not run: SSH stopped responding,
CDC COM17 remained enumerated but failed port configuration (Windows error 31),
and the user confirmed the tablet was frozen. No serial bytes were acquired.
Cause is **unknown**. Earlier successful per-run cleanup is not a current health
check and does not exonerate the candidate, kernel, runtime PM or other components.
Recovery/previous-boot evidence is still pending. No new kernel build/reboot was
performed for this change; no default promotion or further stress testing.

## Delivered source interface

`scripts/stage_camera_app.py` now accepts explicit `--raw-async` (or API
`raw_async=True`). It defaults OFF, with strict JSON/Python boolean validation
also under `python3 -O`. Missing config retains the old OFF behavior. The launcher
sets only `MIPAD2_CAPTURE_RAW_ASYNC`; inherited diagnostic/GST/LD injection is
still stripped. Native RAW_DIRECT, COPY and ALLOCATION_GUARD remain mandatory;
legacy source/decode queues are not enabled. No quality, sensor rate, timestamp,
bitrate or audio policy is changed.

The existing Snapshot tail is a non-leaky four-buffer copied-system-memory
GStreamer queue, not four retained AtomISP MMAP leases. Source:
[CameraTail at the measured app revision](https://github.com/E7G/snapshot/blob/0a7ce87affa902f33599819aed5c4123a548f1c6/aperture/src/mipad2_raw_capture.rs).
Normal encodebin already has its own encoded output queue; this candidate adds
a different boundary immediately after guarded native capture copying.

Opt-in profiles use a `-raw-async` preferences suffix. **This is not a co-install
scheme:** compiled app prefix and desktop file still identify the same app source
revision. Compose into a NEW output tree, never install over the protected
existing prefix or assume two profiles can be installed side by side. Supply
all existing explicit app/plugin/AAC receipt SHA arguments; `--dry-run` remains
available. No system launcher, rootfs preset or automatic lock policy is changed.

154 full flash tests passed normally and under Python `-O`. Five new tests cover
default OFF, malformed input rejection before output creation, profile/hash
serialization, single-switch environment delta with guards, and launcher typing.
A real four-plugin/source-app composition passed host checks; effective profile
environment matches the manually measured B wrapper with identical paths.
The composed package has NOT been installed/tested as a package; rootfs ABI and
complete image remain unqualified. Host success is not hardware acceptance.

## Limited actual front-camera comparison

Both are normal foreground app recordings, native 1920x1080 NV12, fixed VA
rational-rate plugin, AAC 48 kHz stereo; no in-process diagnostic action/tracer.
Auxiliary private kernel tracing was enabled equally for both runs. These are
sequential A/B, not randomized, frequency-matched A/B/A or controlled optical work.

| Measurement | A: synchronous tail | B: copied async tail |
|---|---:|---:|
| Decoded frames | 1002 | 1005 |
| Encoded fps | 29.97185 | 30.00149 |
| Maximum PTS interval | 53 ms | 34 ms |
| PTS intervals >50 ms | 2 | 0 |
| Mean actual VB2 done to DQ | 68.123 ms | 0.283 ms |
| Maximum actual VB2 done to DQ | 135.1 ms | 3.405 ms |
| Owned by driver after done: minimum | 0 | 3 |
| Zero-owned key-window callbacks | 109/1005 | 0/1007 |
| Max measured temperature | 70 C | 72 C |
| Observed CPU ceilings | 1.84/2.24 GHz | 1.84 GHz |

All video frames/audio decoded; no adjacent exact decoded repeats. One B pass
does not erase earlier cadence failures. Generic `vb2:vb2_buf_done` actually
emitted and matched all 1041 A / 1045 B dequeues; trace ring overruns were zero.
The callback follows `owned_by_drv_count` decrement, before waking waiters.
This supports downstream scheduling/driver-buffer-starvation attribution for
these runs, not proof that every long gap or the later freeze is explained.

## Vendor comparison / limits

Pinned Android reference
[atomisp_cmd.c](https://github.com/latte-dev/android_kernel_xiaomi_latte/blob/d2afb1de9a761ff01dafdf9efe4736e521ab71f6/drivers/external_drivers/camera/drivers/media/pci/atomisp2/atomisp_driver/atomisp_cmd.c)
uses `ktime_get_ts` in `get_buf_timestamp` (742-747), called at completion (1207).
It too is a software completion timestamp, NOT measured sensor SOF. Do not
rewrite kernel clock semantics on the assumption the vendor timestamp is SOF.
No new Windows-driver equivalence result is claimed by this comparison.

Scalar results: [machine-readable summary](../tests/mipad2-raw-async-7.2-summary.json).
Raw media, per-frame timestamps/hashes, kernel/pointer/serial evidence remain
tablet-private. Exact timestamp alignment assumes contiguous source frames;
it does not establish physical pixel identity or sensor frame conservation.

Required before promotion: freeze attribution/recovery evidence, repeatable
long A/B/A with thermal/CPU observations, both cameras, reopen and suspend/PM,
live preview/recording behavior, optical AE/AWB/focus and full image qualification.
The complete MiPad2 kernel/system and Android/OEM parity goals remain open.
