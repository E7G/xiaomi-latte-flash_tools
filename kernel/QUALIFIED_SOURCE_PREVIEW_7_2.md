# Mi Pad 2 7.2.15 qualified-source image preview

This is a disposable build preview, not a default image change. The stable
Arch/CachyOS branches and the physical tablet's LPAT31 default are unchanged.
Do not flash these preview artifacts to the current tablet.

## Rebuild from GitHub

1. Select the manual **Build CachyOS DNX package** workflow
   (`.github/workflows/build-dnx.yml`) at the
   `codex/mipad2-72-qualified-image-preview` ref.
2. Pass only the kernel commit
   `603f99209cba3fc41e697890f980f68873f94c52`. The workflow checks that exact
   published commit; changes to a branch head do not change the source pin.
3. Download the kernel package, the non-secret provenance receipt, or the
   explicitly labeled USB/DNX preview artifacts from the completed run.

The pinned [kernel source](https://github.com/E7G/linux_latte/commit/603f99209cba3fc41e697890f980f68873f94c52)
was built, booted once on the physical tablet and returned to stable LPAT31.
The [full kernel build](https://github.com/E7G/linux_latte/actions/runs/46109996857)
and [qualification note](https://github.com/E7G/linux_latte/blob/36c31988d3ed5cb3064f09936a17da7e327a35a1/fix_file/tests/mipad2-72-release-qualification.md)
record its scope. The flash workflow rebuilds the same source for the ALPM
package `linux-latte-integrated-7-2` with distinct release
`7.2.15-mipad2-integrated-r32`. It does not copy the tablet's actual LPAT31
kernel or the qualification kernel's exact bytes. The charger-specific
candidate and later sleep changes are intentionally not in this source pin.

## Build boundary

- The kernel producer uses the digest-pinned x86-64 official Arch container
  and the signed [Arch Linux Archive](https://wiki.archlinux.org/title/Arch_Linux_Archive)
  repository snapshot for 2026-11-25. The package and its receipt come from
  public inputs, not directories, packages or signing keys on the PC.
- The image consumer verifies the produced package's SHA and commit before
  touching a runner's NBD device. The resulting rootfs must contain exactly
  one kernel module release and the matching, embedded source provenance.
- The receipt carries the kernel SDK's package versions and pins, kernel
  artifact manifest, image input commit, rootfs package list, platform-tools
  digest and preview public certificate. Private signing material is not
  published. The independently generated preview key is not that of the
  tablet; no firmware enrollment is requested.
- The DNX package uses Google's versioned Windows Platform-Tools 37.0.3
  archive, not the moving `latest` alias. Its SHA-256 matches the historical
  successful R4 preview receipt. The download/cache is checked before NBD
  or image generation and checked again before unpacking; the new receipt
  records the immutable URL, version and digest. No Fastboot command runs
  during the input check.
- This is not a claim of byte-identical images. Signatures, image metadata
  and the rootfs's live Arch/third-party packages can differ. The image uses
  the stock Snapshot application with the launch helper; the tablet's
  separately sourced native-AE Snapshot deployment and optional GStreamer
  experiment are not bundled here.
- A successful build and read-only image inspection do not prove that this
  image has booted on real hardware. Keep the existing verified LPAT31
  default and recovery entries during separate device qualification.
