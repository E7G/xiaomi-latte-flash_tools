# r5 actual H.264 VME path: diagnostic, not a fix

## CONT31: short same-binary front-camera A/B, experimental

OFF:29.336042 fps/max65.667 ms/14 gaps>50 ms. ON:30.001415 fps/max34 ms/zero gaps
>50 ms. Requested10 s each; complete MP4 spans about14.1 s, not full30-second
qualification. Same private binary,425 measured early preparations only in ON;
installed driver/defaults unchanged. Waiting moves into BRC/constant-data
preparation; whole encoder mean wall remains about26.2 ms, not a total speedup.
Thermal/frequency conditions differ; no Android-parity or source-frame
conservation claim. Both decode/restoration/fault checks pass. Full source-order
host tests/negative controls pass, but sustained/reverse-order/dual-camera and
resume qualification remain open.

[Pinned measured evidence and explicit limits](https://github.com/E7G/linux_latte/blob/49b2748e2a7c11e017349d109a79baa69dd4ff9d/fix_file/MIPAD2_R5_SELECTED_VME_7_2.md).

[Experimental patch only; not installed automatically](patches/experimental/I965_EARLY_IDRT.md).

## CONT30: IDRT preparation is the largest measured MBEnc stall

Two more diagnostic windows still fail full-quality foreground recording
cadence. Actual417-call MBEnc split: IDRT6.921016 s wall/0.047698 s threadCPU;
constant-data preparation1.466834/0.052781 s. Source shares the dynamic-state BO
between GPU-updated CURBE and later CPU-written IDRT. Specific wait/descheduling
attribution is not proven. A two-file early-IDRT candidate builds offline and
passes10,640 BO-layout/descriptor contract cases, but full BRC/MBEnc ordering
and GPU/same-binary A/B qualification remain open. Candidate not deployed.

Two exact obsolete r3 test clips removed with2,479 protected hashes/35 aliases
unchanged; original host timeout recovered from the same finished job, not
reissued. Only ended private caches/backed-up DSOs otherwise removed. All
current failures/references/logs/photos/kernels retained. Final independent
files/control/PM/global-environment audit passes, no reboot or nonzero playback.

[Pinned detailed measurements and explicit limits](https://github.com/E7G/linux_latte/blob/e63bfa9eab598906fa219c414e55a45cfe609c37/fix_file/MIPAD2_R5_SELECTED_VME_7_2.md).

Correction to the earlier post-pack lead: Gen8/CherryView H.264 delegates to
the Gen9 AVC backend. The legacy Gen8 loop had zero calls; the first coverage
guard failure remains recorded, not relabeled as a pass. Corrected hooks show
405 selected calls; VME run wall9.777 s versus threadCPU1.120 s, about92.4% of
whole encoder wall time. Resource allocation is not the dominant phase.

The distinct10 s requested foreground diagnostic still fails cadence:
29.481878 fps, max71 ms, nine gaps over50 ms. Full quality unchanged; exact
GPU/descheduling causes and end-to-end frame conservation remain unproved.
Next seven run subgroups are built and host-tested only, not deployed.
Installed driver/files/settings/35 aliases unchanged; controls restored;
all capture/PCM ended, camera PM suspended, private driver unmapped.
No reboot, nonzero playback or media deletion. Remaining space is just above
2 GiB; no further capture dispatched. No Android-parity or performance fix claim.

[Pinned detailed report and measurements](https://github.com/E7G/linux_latte/blob/7ed8c65020e7cf8be775dd3b60943ff2d36701f2/fix_file/MIPAD2_R5_SELECTED_VME_7_2.md).
