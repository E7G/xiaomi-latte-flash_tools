# Kernel source

Kernel patches and the optimized defconfig live in the
[`E7G/linux_latte` `cachyos-mipad2`](https://github.com/E7G/linux_latte/tree/cachyos-mipad2)
branch.

This image repository resolves that branch to an exact commit, uses the
commit in the build cache key, and compiles `xiaomipad2_defconfig` directly.
Do not add a second kernel patch or config overlay here.

The generated kernel package also carries the matching AtomISP firmware,
ALSA UCM, BCM4356 board data, USB serial debugger, recovery helpers, and
hardware smoke test from the same source commit.
