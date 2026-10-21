# Integrated Linux 6.14 kernel source

This candidate image branch uses [E7G/linux_latte
`codex/mipad2-6.14-integrated`](https://github.com/E7G/linux_latte/tree/codex/mipad2-6.14-integrated).
The original `arch_linux` image branch and `cachyos-mipad2` kernel branch are
not changed by publishing this integration branch.

Builds are manual only and require an explicit published 40-character kernel
commit. The workflow obtains its committer timestamp and pins both cache and
package provenance to that commit. The builder rejects kernels outside 6.14.
It builds `xiaomipad2_defconfig` directly, without secondary config/patch overlays.

`stage_kernel_support.py` copies the tracked `fix_file/packages/<package>/`
sources, not generated makepkg `src/` directories. It verifies all sources
before copying and records destination hashes/modes in the package's
`usr/share/doc/linux-latte-cachyos/support-payload.json`. Firmware, ALSA UCM,
board data, no-idle/recovery/camera helpers and the USB serial suspend/resume
hook come from the same pinned kernel source. Cache keys include the stager.

Host build/staging evidence is not a completed DNX image or an on-device
acceptance test. The later r26 device checkpoint includes dual-camera recording,
but the stock-Snapshot rootfs still lacks the tested camera package. See
[the camera source-packaging gates](CAMERA_INTEGRATION.md); portable packaging,
full-image boot and user-visible acceptance remain unqualified. Keep a
validated stable recovery/default boot entry during candidate testing.
