# 7.2 camera recording: userspace rational-rate fix, cadence still open

Requested kernel upstream remains `9928c7b8d00c500ee97903afa1cc76c1c36ab2bc`
(7.2.0). Current physical test kernel remains `7.2.0-mipad2-integrated-r3`;
no new kernel C change or build for this userspace defect.

Source fix, reproducible host oracle, pinned three-plugin build and scalar
hardware evidence are published in Snapshot commit
[`806b5ef1baa980c2b6ebacb40eccfe99dc5ae335`](https://github.com/E7G/snapshot/commit/806b5ef1baa980c2b6ebacb40eccfe99dc5ae335) on
`codex/mipad2-7.2-integrated`:
[full report](https://github.com/E7G/snapshot/blob/806b5ef1baa980c2b6ebacb40eccfe99dc5ae335/MIPAD2_VA_FRAME_RATE_7_2.md).

GStreamer VA BRC previously masked native 78125/2604 fps into 12589/2604;
nearest bounded rational packing restores a representable near-30 fps parameter
without changing source caps, PTS, bitrate requests, sensor programming or quality.
The actual generic production parameter dispatcher/helper is exercised under
ASan/UBSan; 384 production cases plus 3969 exhaustive reduced-bound oracle cases.
All 41 combined plugin/AAC/app builder tests pass normally and under Python -O.
An initially stale AAC helper pin was detected by full discovery and corrected.

Same-build 300-frame native video-only comparison: baseline 84.90 Mbps,
27.332 fps, maximum PTS gap 863.667 ms; fixed 15.95 Mbps, 30.002 fps, max 34 ms.
Exact tested plugin and i965 mapped in the process. This validates the scoped
VA bitrate defect, not complete application recording.

**900-frame full-recipe long test still FAILED cadence:** 15.23 Mbps, 29.737 fps,
one 301.333 ms PTS gap at about 20.165 seconds, not startup. No startup frames
excluded. Earlier normal foreground source app with AAC (old plugin) had three
>50 ms intervals in 909 frames, maximum 56.667 ms; its remaining cadence is NOT
proved fixed by the new rational patch. Its old-plugin bitrate already normal.
Raw V4L2 baseline was about 30 fps/max33.889 ms; kernel timestamps represent
buffer completion, not physical sensor SOF. Do not infer frame conservation.

New VA plugins are only privately staged diagnostic artifacts, not installed
into the default launcher/rootfs or promoted as smooth normal-camera recording.
Existing pinned source app/AAC/flash package identities remain their original
historical artifacts; their successful gates are not relabeled as new builds.
Stable GRUB fallback, installed boot/system files, authentication and lock
policy preserved. No audible playback. Camera clients closed; both sensors/ISP
suspended, no kernel fault markers; 686 protected files and 35 private aliases
and bytes unchanged after qualification. Raw video, per-frame metadata/timing,
kernel logs and serial traces remain device-private.

Open gates include attribution/fix of long gaps, normal-app preview/video/audio
and rear-camera validation with matching plugins, optical AE/AWB/focus quality,
7.2 acoustic/UCM, resume/S0I3, S5 cold boot, and failed-reset DMA quiescence.
No complete image, Android/OEM parity or full MiPad2 task completion claimed.
