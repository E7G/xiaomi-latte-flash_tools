# Camera packaging gate: not yet closed

This document is a candidate-branch integration ledger, not a completed image.

## Pinned source checkpoint

- Kernel source remains [E7G/linux_latte integrated6.14](https://github.com/E7G/linux_latte/tree/codex/mipad2-6.14-integrated).
  The tested r26 binary was built from `6074419168fbb70aa5685e976874da6cf86d1fae`;
  subsequent documentation commits do not mean a new kernel was built or booted.
- The source-preparation recipe is published in [E7G/Snapshot commit
  ba75ca25](https://github.com/E7G/snapshot/tree/ba75ca25c7689c4a974cc0c1c8af28a7db427885/contrib/mipad2/portable-plugins).
  It pins three existing functional GStreamer1.28.7 patches/official archives and
  resulting source hashes. It does not package the app, AAC, private V4L2 plugin,
  desktop launcher or complete camera stack.
- [Ordinary-power device evidence](https://github.com/E7G/snapshot/blob/ba75ca25c7689c4a974cc0c1c8af28a7db427885/MIPAD2_R17H_ORDINARY_POWER.md):
  four entire1080p H.264/AAC clips, two fresh processes/reversed camera order,
  approximately30fps, maximum PTS gap34ms, no intervals>50ms. This is NOT
  foreground optical/Android parity or a new image acceptance result.

## Current rootfs gap

`build_rootfs.sh` still installs the distribution `snapshot` package. It does not
build pinned E7G/Snapshot sources or stage the tested functional plugin stack.
`stage_kernel_support.py` supplies firmware/board data/ALSA/serial/recovery/test
helpers from one pinned kernel SHA; it is not a camera application package.

Do not copy device `/var/tmp` plugins or call stock Snapshot equivalent to the
tested candidate. Their dependency/provenance differences must be resolved first.
The local `device_files/mipad2-camera-af.c` modification is unrelated pre-existing
work and was not folded into this source-packaging checkpoint.

## Required next gates

1. Build Snapshot from an explicit published40-character SHA and its Cargo.lock;
   build the three source plugins in a matching1.28.7 development environment.
   The recipe has13 passing contract tests normally/`-O` and verified real patch
   application, but this host's1.28.4 ABI was rejected BEFORE compilation. There
   is no completed portable-plugin build or target installation from that tool.
2. Resolve AAC/runtime ABI and stock-V4L2 equivalence explicitly. Keep diagnostic
   tracers out of a production bundle, retain functional app capture-copy lease
   isolation, and do not resurrect rejected R17i encode-input queue policy.
3. Install only an isolated, versioned candidate first; qualify both physical
   cameras, full-native photos, whole-clip full-quality recording, reopening,
   rotation, resume and visible preview. Preserve stable launcher/recovery.
4. Only after those gates, add an explicit opt-in camera source builder/stager
   and provenance manifest to image creation. Then perform full-image build,
   flash, S5 cold boot and broad hardware/OEM/Android-Windows comparison.

No default kernel, launcher, rootfs source pin, automatic build/flash trigger,
power policy, or original `arch_linux`/`cachyos-mipad2` branch changed here.
