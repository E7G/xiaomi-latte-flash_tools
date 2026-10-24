# r5 actual H.264 VME path: diagnostic, not a fix

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
