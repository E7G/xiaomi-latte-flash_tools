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

## Verified input and kernel outputs

- [R32 build 46117291288](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46117291288)
  produced the native ALPM kernel package with SHA-256
  `d7e2791f5e1d5c449213ecbe4ebd5629da4181c45e0cfddcc908b3024da40b47`.
  An independent Arch package query and payload/manifest check passed.
  It contains 37 compressed modules; all 19 explicitly checked board
  configuration options match the previously booted qualification build.
  The Arch build uses Clang/LLD 23.1.5, not the Ubuntu 18.1.3 toolchain
  of the earlier physical qualification. The R32 binary itself has
  not been booted on the tablet.
- [Windows input run 46119224717](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46119224717)
  passed four fetch/cache and 35 kernel-handoff fixture tests. It fetched
  Google's versioned 37.0.3 archive, verified the SHA-256 against the
  historical successful R4 receipt, and checked the ZIP and revision
  without executing Fastboot.
- The R32 kernel was built before the new Fastboot gate was committed.
  The full image run and the Fastboot-input qualification are separate
  receipts, not a claim that the original image run used the new gate.

## R32 package boot and remaining USB-image gate

[Package VM run 46120201235](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46120201235)
booted the exact ALPM package's kernel (SHA-256
`a23bb6597fc269825ec356d60bc2dca34de95a4cfd08bbb32163ed8d884d010e`)
through isolated OVMF/GRUB. It reported R32 and the default-off PMC event,
rejected an EROFS control with only its signature removed, and loaded 11
original signed modules with enforcement active. The guest had no network,
production storage or real Mi Pad 2 peripherals; this proves the packaged
kernel boot, not image boot, Secure Boot enrollment or hardware parity.

After the complete USB artifact is available, invoke
`scripts/boot_r32_usb_preview_vm.sh IMAGE.img.xz SHA256 EMPTY_OUTPUT_DIR`
on a Linux validation host with the isolated VM tools. It checks the XZ
hash, GPT and image size, then instruments only a disposable raw copy's
GRUB menu for serial output. The original EFI binary, kernel,
root UUID, subvolume and initramfs are retained. The virtual board is
not identified as Mi Pad 2, the installer is masked, the VM has no
eMMC and no host disk is attached. This distinguishes actual image
firmware-to-userspace boot from the narrower package smoke test.

## Completed USB/DNX publication and virtual userspace boot

[Full build 46117291288](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46117291288)
published the R32 kernel package, USB image, DNX preview and provenance
receipt. The original image used the same Platform-Tools archive bytes
now pinned by the separate input gate. Its USB XZ SHA-256 is
`13fb799feb7e7ea1827511a71c8b088a6514b592463c339543145433169d9c3a`.

[USB VM run 46121085850](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46121085850)
verified that exact compressed artifact, preserved the EFI binary and
the original kernel/initramfs and Btrfs root selection, and booted its
diagnostic copy through OVMF/GRUB into the R32 kernel and `mipad2 login:`.
The preview installer was masked and there was no guest eMMC, live disk
or network. This is a rootfs boot result, not a flash/install, GNOME
session, user-data restore or physical Mi Pad 2 boot result. These
products remain labeled not for production.

The actual rootfs uses GNOME Shell 51.1 and stock Snapshot 51.0. The
producer log directly reports skipping the compact on-screen keyboard
patch because the old helper supports only GNOME Shell 50.x. Merely
finding the helper and Pacman hook in the image does not qualify the
compact keyboard on 51.1. The official signed Arch 51.1 resources still
contain the four-row default/shift layout and the three keyboard theme
files, so a version-specific resource test is available for the next
compatibility change. Neither this gap nor the separate native-AE
application was resolved by reaching the console login prompt.

## GNOME 51.1 userspace follow-up

The new keyboard helper accepts the exact Arch GNOME Shell 51.1 package
`1:51.1-1` and checks the signed stock-resource digests before modifying
anything. It preserves the four-row extended input and the old width and
spacing adjustments without dropping unrelated resources. Other 51.x
packages are not assumed compatible; the legacy 50.x profile remains.
The full image workflow now compares the installed resources with the
complete plan in read-only mode. This supplements, not replaces, a
real graphical touch-keyboard test.

For a userspace-only rebuild, keep the same `kernel_commit` and pass
`-f reuse_verified_r32_kernel=true` to the documented DNX workflow.
This opt-in still verifies the original run, immutable package SHA and
current package handoff, but avoids rebuilding the VM-qualified R32
kernel. It requires that the old artifact is still retained. Leave the
option off to rebuild from the pinned source and SDK after it expires.
Neither choice modifies the physically installed LPAT31.

[Stock-resource test 46121998421](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46121998421)
passed on the official Arch 51.1 assets, both normally and under optimized
Python. The exact two layouts and three theme CSS assets changed; all
other resource paths and bytes matched stock. Widths and offsets scale
without changing key labels or actions. The test also covers read-only
verification, idempotent reapplication, wrong stock digest, unknown
versions and rollback after simulated failure of the second write.
[Image run 46122185819](https://github.com/E7G/xiaomi-latte-flash_tools/actions/runs/46122185819)
passed the immutable R32 package handoff with compilation skipped. Its
rootfs/USB/DNX rebuild is a separate in-progress qualification. No
physical device configuration was changed.

The rebuilt image run's read-only chroot verification passed after mounting
its actual rootfs: `Mi Pad 2 compact GNOME OSK verified`. The receipt confirms
GNOME Shell 51.1, the unchanged R32 package bytes and pinned Windows
Platform-Tools 37.0.3. The new USB XZ SHA-256 is
`c6f06a54c2d3482de4b671f37e64eb5a41648addb5b299586410f0332ddc5c88`.
Its independent EFI-to-console boot uses that digest; the previous
USB artifact has separate historical boot evidence. Installed resources
are verified, but graphical touch interaction is not yet qualified.
