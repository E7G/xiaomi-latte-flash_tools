# 7.2 board PLL resume dependency

Pinned [source, hardware comparison and regression tests](https://github.com/E7G/linux_latte/blob/69bb7d3fbea73093bed7b7bcf060472ecb5bfea0/fix_file/MIPAD2_PLL_RESUME_7_2.md).

Follow-up to PLL_DSP_LIFECYCLE_7_2.md: conditional codec I2S/PLL routes alone
lost PLL power after resume. The board switches from RC to PLL in PRE_PMU,
after DAPM has already computed supply demand. An unconditional board
Platform Clock -> PLL dependency resolves that ordering without forcing pins
or adding a resume repair script.

Baseline failure reproduced; two consecutive corrected 12-second RTC cycles
passed OS/sleep and actual hardware clock/amp-ready checks during digital-zero
PCM. No new audible listening test, kernel installation or cold boot this turn.
Production machine module W=1/Clang21/thinLTO/modpost passed. Host production-C
fixtures pass normal/-O; the actual prior source fails both negative controls.

The tablet still runs original 7.2r3 with two temporary, non-autoloaded DAPM
overlays. Reboot loses them. Full integrated build/install/cold-boot qualification
is next; this is not an already deployed permanent kernel fix. Stock TFA bypass
remains selected, factory DSP/MTP untouched. Full acoustic/OEM qualification,
idle graph power and earlier long-run/camera issues remain open.
