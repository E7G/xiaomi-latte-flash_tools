# MiPad2 7.2 r4 deployed: permanent PLL fixes

Full kernel image built from `69bb7d3fbea73093bed7b7bcf060472ecb5bfea0`,
stock TFA bypass and exactly the prior r3 config. All 31 module CMS signatures
verified; native Arch package passed query/preflight (not locally PGP-signed).
The device was staged separately, not installed via pacman. Rescue default
preserved; exactly one guarded warm reboot reached the r4 image.

No temporary PLL route modules were loaded. Both consecutive 12-second RTC
cycles passed OS/sleep and actual PLL/two-amp-ready hardware checks using digital
zero only: S0I3 increments 11738176 and 12070080 us. Trace shows PLL power-off
and correct power-on, not forced-on sleep. 51 discovery smoke checks and 2163
protected installed-file checks passed; no new fault markers. Raw traces remain
device-private. Three existing full-build LTO frame-size warnings retained.

This is not S5 cold-start, new human acoustic, optical recording, long-run DMA,
factory-DSP or Android-equivalence qualification. Full OS image not built.
Factory DSP/MTP untouched. Idle audio graph power and wider device work remain
open. See the pinned kernel report and scalar hashes/evidence:

[r4 deployment report](https://github.com/E7G/linux_latte/blob/b1be4f70b3494de008021b804cb9830aae2134a1/fix_file/MIPAD2_R4_DEPLOYMENT_7_2.md).
