# 7.2 PLL sound-path and factory DSP lifecycle work

Pinned [source, real hardware evidence, tests and explicit failures](https://github.com/E7G/linux_latte/blob/13abdd804e493b301a2a1115f664632063107c62/fix_file/MIPAD2_PLL_DSP_LIFECYCLE_7_2.md).

The current7.2r3 stock/bypass backend produced no sound: selected PLL SYSCLK but
RT5659 PLL power was off; both amp PLLs were unlocked.33 read-only owning-regmap
cache/hardware samples agreed, ruling out a simple stale-cache explanation for
this capture. Conditional direct I2S1/2/3->PLL routes restore hardware readiness.
A temporary exact-source DAPM overlay restored both tones, human-confirmed at the
same waveform/stream/sink volume. Production RT5659 module compiles and links.

The overlay is temporary/no boot autoload; the originalr3 kernel image is unchanged.
The RTC resume itself passed but later hardware reads caught PLL off again:
**post-resume audio FAILED**, not a stable-kernel endorsement. The failed evidence
is preserved. One overlay reapply restored hardware readiness; no automated resume
workaround or second suspend. No human post-resume/reapply listening confirmation.
Full integrated kernel rebuild/install/reboot/resume still required.

Separately factory mixer POST_PMU/PRE_PMD now drives its existing worker lifecycle;
no_pcm amp links do not receive the separate RT5659 C2C link's mute callback.
Factory module W=1/thinLTO compile passes but remains unbound, defer=true/stock
selection unchanged. Factory music/speech have one volume step each; bypass lacks
VP data, so no invented multi-step master-volume policy. Calibration/MTP policy
and DSP-aware UCM still required before factory activation.

10 positive and4 intended negative host commands pass; ASan/UBSan and actual-core
sequence checks are not physical DSP proof. Read-only diagnostic unloaded; external
module taint recorded. Raw traces remain tablet-private. No cold boot/new kernel,
forced I2C/cache writes/OTP programming. Prior hang/DMA, full camera/PM/OEM image
and complete audio qualification remain open.
