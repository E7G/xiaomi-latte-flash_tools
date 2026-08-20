# Kernel patch provenance

- `0001-cachyos-base-6.14.patch`: `[PATCH 5/9] cachy`, extracted unchanged from CachyOS `kernel-patches/6.14/all/0001-cachyos-base-all.patch`.
- `0002-bore-cachy-6.14.patch`: CachyOS `kernel-patches/6.14/sched/0001-bore-cachy.patch`.
- `latte-cachyos.config`: Mi Pad 2-specific config fragment layered on `xiaomipad2_defconfig`.

`linux_latte` already carries the newer EEVDF `RUN_TO_PARITY` condition. The conflicting BORE hunk is omitted from `0002`; `scripts/build_kernel_package.sh` applies its equivalent to that newer condition before configuration.
