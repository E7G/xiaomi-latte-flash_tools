# Rebuild the Mi Pad 2 7.2 snapshots from GitHub

Use the build target for each component. Do not substitute an image kernel for the
kernel installed during the physical LPAT31 validation.

| Target | Source and behavior |
| --- | --- |
| LPAT31 kernel bundle | linux_latte source `3f4956789e34da213332510246d565920a23578c`, the original resolved configuration, LLVM 18 and the original list of 37 modules. The workflow checks the source, exact release, configuration, module inventory and signatures. |
| R4 USB and DNX preview | linux_latte source `dc91bb020245527cab80bae5cfc64c2b8079c9b2` built from source as `7.2.15-mipad2-integrated-r4`. This Flash branch preserves the seven reviewed changes beginning with combined commit `36783252f2837ea183e70caf61e142c58d08e6e9`. It uses the fresh-image GNOME profile, not a dump of any physical tablet. |
| 7.2.15 qualified-source USB and DNX preview | [R32 rebuild and limitations](../kernel/QUALIFIED_SOURCE_PREVIEW_7_2.md). It rebuilds the source physically booted as the combined qualification kernel, not the exact installed LPAT31 image or per-user tablet state. |

For the newer qualified-source image preview rather than the historical R4
run, use:

```bash
gh workflow run build-dnx.yml -R E7G/xiaomi-latte-flash_tools \
  --ref codex/mipad2-72-qualified-image-preview \
  -f kernel_commit=603f99209cba3fc41e697890f980f68873f94c52
```

Artifacts from this independent preview are not a physical device dump,
flash approval, or a replacement for LPAT31. The branch also retains the
separate verified Denial and native-AE Snapshot rebuild paths below.

For LPAT31 and the historical R4 preview, run from any directory with an authenticated GitHub CLI:

```bash
gh workflow run mipad2-72-daily.yml -R E7G/linux_latte \
  --ref codex/mipad2-72-lpat31-replay -f variant=lpat31

gh workflow run build-dnx.yml -R E7G/xiaomi-latte-flash_tools \
  --ref codex/mipad2-7.2-guarded-release-preview \
  -f kernel_commit=dc91bb020245527cab80bae5cfc64c2b8079c9b2
```

After successful runs, download the artifacts using
`gh run download <run-id> -R <owner/repo> -D <empty-directory>`.
Use the LPAT31 bundle's SHA-256 file or the USB image's SHA-256 file to verify
downloads. The one-click folder contains its own `SHA256SUMS`. The R4 receipt
records both source pins, the kernel package hash, the rootfs package inventory,
the Arch container digest, Platform-Tools checksum and public preview certificate.
Actions artifacts expire; the source branches and build instructions are the
long-term way to rebuild them.

The scope is source and behavior reproduction, not bit-for-bit identity:
module signing identities are generated per build; the R4 preview also uses a
new EFI test identity and the rolling Arch repositories and Android Platform-Tools
distribution. The preview certificate is not the key enrolled on a physical
tablet and no signing private keys or physical-device files are needed or uploaded.
This workflow does not flash hardware or reproduce a user's installed desktop data.

## Physical desktop and camera

The GNOME preview is not the tablet's Denial session. The deployed Denial
QuickTile source is pinned to `ff56879745b9c8c4e1c07e1934ef627c00ffdacd`.
Its [verified cloud build](https://github.com/E7G/linux_latte/actions/runs/44244515448)
and exact branch are separate from the kernel and flash image:

```bash
gh workflow run mipad2-quicktile-desktop-build.yml -R E7G/linux_latte \
  --ref codex/mipad2-72-denial-replay
```

The tablet's currently active Snapshot executable is **native-AE r6**,
source `db794b2fe85c72dd77710880bbc45ca3909ace1a`, not the earlier
15 fps installation candidate. Rebuild it with the
[Snapshot replay workflow](https://github.com/E7G/snapshot/blob/codex/mipad2-72-snapshot-replay/docs/MIPAD2-72-REPLAY.md).
The [native-AE launcher fixture](fixtures/mipad2-camera-launch-native-ae-r6)
records the live launcher after the bounded focus-startup change. It uses
the [qualified focus helper](https://github.com/E7G/xiaomi-latte-flash_tools/blob/b57ba7ab486dfc251c199463efb6636e22507b28/device_files/mipad2-camera-init-focus)
from PR #45. The fixture is not automatically included in the DNX image and
does not replace the image's default camera target.

### Native-AE cloud artifact against the physical LPAT31 runtime

[Snapshot run 46109195747](https://github.com/E7G/snapshot/actions/runs/46109195747)
built the same native-AE source. Its archive SHA-256 is
`7fa71e0b63832ebb7e7439df1265e80df10515889afc8ecb39b303082b6bbede`.
Its executable SHA-256 is
`5ea70f161f3cc4b6503030c890c39c64780ab001045072fe2d29c46d3ee718d9`,
not the installed
`f16944d2b075af0ad6aa75e465036a5520fb00a74b0180d4bf433968f6a6b3d6`.
Hashes identify this run, not every future rebuild of the source.

The signed-host connection used private tablet tmpfs to check the exact cloud
binary without entering the app. The system loader resolved the same 136
entries for the cloud and installed executables; both were x86-64 with the
system interpreter and no RPATH/RUNPATH. Relocation checks found no missing
libraries or undefined symbols on LPAT31 with GStreamer 1.28.7-1.
The GLib schema XML and GResource were byte-identical to the installed ones;
the extracted schema passed strict GLib validation.

No Snapshot main, camera stream, or restart was run. The ISP was runtime
suspended before and after, the temporary files were removed, and the live
launcher was not changed. This is evidence for the actual userspace ABI and
resource inputs, not new front/rear image-quality, frame-interval, or
successful-preview qualification of the cloud executable. The independent
USB/DNX preview still uses the stock application.

Do not erase signing/trust backups, local hardware-test evidence, rollback
media, or the tablet's per-user configuration on the assumption that these
builds recreate them. This procedure only replaces the listed build inputs.
