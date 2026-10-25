# Experimental IRQL AVC early-IDRT candidate - NOT a default driver

This artifact is for review and controlled validation only. No build, install,
boot or package script applies it automatically. It is not an upstream Linux
kernel patch and is not part of the separate RT5659 upstream PR.

Base: IRQL intel-vaapi-driver2.4.5 commit
`0b648be50cd80e16469c135c76ff61bbd2f2d12b`. The patch changes exactly
`src/i965_avc_encoder.c` and `src/i965_avc_encoder_common.h`: prepare the regular
non-FEI MBEnc descriptor before BRC writes the shared dynamic-state BO, and
skip the later descriptor rewrite only for the same context with fresh per-frame
readiness. It does not bypass synchronization or BRC, lower quality, replace
frames, retime timestamps or force clocks. The pure patch enables its reorder
when applicable; the PID/file-scoped ON/OFF gate used in diagnostics is separate
test instrumentation, not included in this patch.

A short same-binary front pair and one instrumented full30-second front
interval now pass cadence. Observed clip metadata joins963 frames, but this is
not physical sensor-SOF or pixel-payload identity. Rear stopped at80 C after
about4 seconds; sustained rear, repeated/reverse-order, uninstrumented, thermal
endurance, resume/reopen and real hardware fault paths remain open. Waiting
was redistributed, not eliminated. Do not deploy as a validated fix.

[Full interval evidence and limits](https://github.com/E7G/linux_latte/blob/a4642afd95379ef4a5c90dcb90fc70ed5d2e8e29/fix_file/MIPAD2_R5_SELECTED_VME_7_2.md).

Patch SHA256:
`e3f697ddcc50abb3ca155a228d8d624b2dc756543b42d8849ef0adb824c7c3f0`.

[Detailed pinned evidence and limits](https://github.com/E7G/linux_latte/blob/49b2748e2a7c11e017349d109a79baa69dd4ff9d/fix_file/MIPAD2_R5_SELECTED_VME_7_2.md).
