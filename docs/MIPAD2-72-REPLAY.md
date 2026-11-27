# Rebuild the Mi Pad 2 7.2 snapshots from GitHub

There are two separate build targets. Do not substitute the image kernel for the
kernel installed during the physical LPAT31 validation.

| Target | Source and behavior |
| --- | --- |
| LPAT31 kernel bundle | linux_latte source `3f4956789e34da213332510246d565920a23578c`, the original resolved configuration, LLVM 18 and the original list of 37 modules. The workflow checks the source, exact release, configuration, module inventory and signatures. |
| R4 USB and DNX preview | linux_latte source `dc91bb020245527cab80bae5cfc64c2b8079c9b2` built from source as `7.2.15-mipad2-integrated-r4`. This Flash branch preserves the seven reviewed changes beginning with combined commit `36783252f2837ea183e70caf61e142c58d08e6e9`. It uses the fresh-image GNOME profile, not a dump of any physical tablet. |

Run from any directory with an authenticated GitHub CLI:

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
  --ref codex/ci-quicktile-screenshot-ff56879
```

The tablet's Snapshot 15 fps display preview uses the
[separate Snapshot replay workflow](https://github.com/E7G/snapshot/blob/codex/mipad2-72-snapshot-replay/docs/MIPAD2-72-REPLAY.md).
It pins the local installation recipe; scaling, extra buffers and direct NV12
are separate experiments, not active image defaults.

Do not erase signing/trust backups, local hardware-test evidence, rollback
media, or the tablet's per-user configuration on the assumption that these
builds recreate them. This procedure only replaces the listed build inputs.
