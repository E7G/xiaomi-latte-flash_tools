# Factory TFA9890 candidate for 7.2: source port, not activated audio

Pinned [kernel source changes, build and exact limits](https://github.com/E7G/linux_latte/blob/50aa492d3545539a11a7bcda0ad79e04e97949e7/fix_file/MIPAD2_FACTORY_DSP_7_2.md).

Real full W=1/LTO module compile first failed removed ASoC APIs; current APIs now
compile/link the three-object factory module. Local OUT/HiFi Playback names match
the current board's Left/Right prefixes. Mixer templates are immutable with per-amp
profile pointers; allocation/control-registration errors propagate. Firmware metadata
declares tfa98xx.cnt. Actual-probe ASan/UBSan fixtures check two instances/six failures;
the API-only old namespace fails the intended board-ABI gate. Eight host commands pass.

Kconfig previously allowed stockm+factorym (!m=m); real solver reproduction and fix
now permit factory only with stock=n. Three-choice matrix passes; separate factory-r4
config only, not a bootable kernel. Default stock selection and running r3 unchanged.

Final .koSHA b21af433e6d37da814cbead99cb5c76bc1b477d578632eb74268e51721590808,
vermagic7.2r3, compilerClang21. Existing r3.config/symvers/vmlinux/bzImage/release
hashes unchanged. Module NOT installed, bound or loaded on the tablet. Compilation
uses exported r3 symbols, not proof of a full mutually exclusive candidate build.

Android Intel-Latte source and local factory container CRC/34+37device records were
inspected; Windows SST INF identifies Xiaomi A3 TDM loopback, not CoolFlux firmware
equivalence. No Windows binary executed or source archives altered.

This candidate exposes Left/Right Profile/Master Volume/Stop, not bypass Amp Input.
Current UCM8 is NOT its final policy. DSP-aware UCM, C2C/no_pcm clock/lifecycle,
firmware profiles/calibration, full kernel/package/serial/rescue and physical tests
remain required. defer_dsp_start=true kept. No forced driver hot switch/firmware write
or audible output. Existing tablet stock bypass/normalvolume/rescue preserved; actual
DSP/OEM sound, previous freeze/DMA and complete image qualification remain open.
