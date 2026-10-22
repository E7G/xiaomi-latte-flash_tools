# Integrated 6.14 binary package and image-input gate

2026-10-21. This closes a package-format/integration gap, **not** full device,
DNX image, Secure Boot upgrade or Android/Windows parity acceptance.

## Actual artifact

The existing completed r26 bundle, not a fresh compile, was repackaged through
real unprivileged Arch `makepkg`. Kernel source is
`6074419168fbb70aa5685e976874da6cf86d1fae`; release remains
`6.14.0-mipad2-integrated-r26`. This does not change the running tablet kernel.

| Input/output | SHA256 |
| --- | --- |
| Completed r26 bundle | `8f28943fb55fceecf5a147969daea543c9fb4883b55ffee733744601ba2b16b1` |
| Public module DER certificate | `3784d19dd5020fb996e1f2c79ab9be8e30ca90b4e06761badc52ae597e74bf94` |
| Final `linux-latte-integrated-6.14.0.r26-1-x86_64.pkg.tar.zst` | `be486e55d12e47deb6a5d7d1e8fa5e2d7f2b38b685ceedbf8f7176b9d59ff884` |

The package is 37,688,784 bytes. It preserves all 52 original bundle files,
including 34 signed compressed modules. Its 56 payload files add only the
package-base marker, module-tree kernel alias, matching mkinitcpio preset and
public module certificate. Real makepkg generates `.PKGINFO`, `.BUILDINFO`,
and `.MTREE`; no `.INSTALL` or private key is shipped. No strip/debug rewriting
of signed kernel/module bytes occurs. The public module certificate is **not**
the EFI MOK, and the local package itself is not PGP-signed.

`scripts/package_integrated_kernel.py` independently re-verifies all 34 actual
detached module CMS signatures against the separately pinned certificate,
checks vermagic and x86 kernel release, and compares every packaged payload
byte. It uses a controlled packaging epoch; this is not a claim that arbitrary
makepkg host environments generate identical `.BUILDINFO` or package hashes.

```sh
sudo python3 scripts/package_integrated_kernel.py \
  --bundle /absolute/path/mipad2-6.14-integrated-r26.tar.zst \
  --bundle-sha256 8f28943fb55fceecf5a147969daea543c9fb4883b55ffee733744601ba2b16b1 \
  --cert /absolute/path/signing_key.x509 \
  --cert-sha256 3784d19dd5020fb996e1f2c79ab9be8e30ca90b4e06761badc52ae597e74bf94 \
  --output /absolute/path/new-separated-output-directory \
  --epoch 1792505535
```

Requires an existing non-root `nobody` account plus makepkg, pacman, fakeroot,
bsdtar, zstd, modinfo and OpenSSL. Root is used to arrange unprivileged makepkg,
not to install the package. Existing output directories are rejected.

## Image and upgrade integration

`build_rootfs.sh` now derives the kernel base from the installed module-tree
`pkgbase`, rejects multiple kernel releases, mismatched explicit bases and
integrated releases outside 6.14, while retaining legacy CachyOS support.
Supplying `KERNEL_PACKAGE_SHA256` requires an explicit `KERNEL_PACKAGE` and
validates the exact integrated package **before** NBD/image operations:

```sh
python3 scripts/preflight_integrated_kernel_package.py \
  /absolute/path/linux-latte-integrated-6.14.0.r26-1-x86_64.pkg.tar.zst \
  --sha256 be486e55d12e47deb6a5d7d1e8fa5e2d7f2b38b685ceedbf8f7176b9d59ff884
```

For a subsequent separately planned image build, use the same explicit package
and SHA through `KERNEL_PACKAGE` / `KERNEL_PACKAGE_SHA256`, optionally
`KERNEL_PKGBASE=linux-latte-integrated`. The image builder is not a dry run:
its existing `all()` path removes named old images. No complete image build
or flash was performed here. The package preflight checks the pinned original
payload hashes and metadata; it does not claim a second CMS verification.

ALPM preflight/install hooks now cover both supported package bases. The install
hook consumes `NeedsTargets`, verifies one package-owned kernel image per base,
retains ESP/Secure Boot preflight and atomic signed-image replacement, and
rejects ambiguous manual autodetection. Real MOK signing, on-device package
upgrade, initramfs/GRUB and boot acceptance remain untested for this new path.

## Evidence and open gates

- 87 unique flash-tool unit/contract tests pass normally and with Python `-O`,
  with no ResourceWarning. Signing tests use fixtures, not an enrolled real MOK.
- The actual final package passes host and tablet-native `pacman -Qip/-Qqlp`
  queries, required-path checks and final image-input preflight.
- Query is not installation: no package transaction, reboot or stable-default
  change was performed. The running r26 kernel and recovery entry remain intact.
- A separate normal camera launch with the display independently powered on
  still had an inactive accessible window and no camera owner. This narrows the
  next camera investigation to foreground/authentication activation; it is not
  proof of a driver black screen or permission denial. No background-capture
  workaround was enabled.
- The existing system no-idle service was active but did not prevent Denial's
  own DPMS timeout. At the user's request, only Denial's persisted
  `power.idleDpmsEnabled` was changed from true to false through its revisioned
  settings API. Lock authentication, lock timeout, power-key and suspend policy
  were retained. This device setting is not an image-wide default change.
  All 21 read-only samples over 630 seconds reported display power on and no
  pending output transaction. On 2026-10-22 the device was found back on the
  stable bqdiag1 kernel; the persisted DPMS-disable setting survived that reboot.
  New r26 runtime tests must not be attributed to this stable-kernel session.
- Native photos, actual foreground preview/recording with the new source-built
  application, motion/AE/AWB/focus, camera-used suspend, complete image boot and
  broad hardware/battery/Wi-Fi/touch/audio parity still need acceptance.

Scalar evidence: [`tests/integrated-kernel-delivery-summary.json`](../tests/integrated-kernel-delivery-summary.json).
No raw media, device logs, personal settings documents or private keys are
published in that summary.
