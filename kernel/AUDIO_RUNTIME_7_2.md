# 7.2 actual audio runtime application and remaining vendor DSP gap

[Pinned kernel source/evidence](https://github.com/E7G/linux_latte/blob/c0dec882c918703bcb01a647ef71b7d32d4b7077/fix_file/MIPAD2_AUDIO_RUNTIME_7_2.md).

Installed UCM8 files were correct but actual live speaker selectors were Left/Left.
With no clients/PCM, temporary sink mute + WirePlumber-only reload applied Left/Right;
exact normal volume/mute/default device/profile restored. ALSA selectors retained
across one12s s2idle/S0I3 return (11.602976s PMC increment), with no kernel errors.
This is control-level retention, not independent on-wire or acoustic verification.

One6s digital-zero source flowed through normal PipeWire playback: RUNNING observed,
exit0, no new kernel/xrun markers, channel selectors and volume/mute unchanged.
Original3s-after-EOF idle gate failed and is retained; later SAME playback was closed
and nodeSUSPENDED. Configured idle default5s made3s premature, but exact close latency
was not measured, no repeat playback or retroactive full-pass claim.

Actual kernel binds both amps to built-in tfa989x, which bypasses CoolFlux DSP.
Present tfa98xx.cnt and unselected tfa98xx-xiaomi source do not prove vendor firmware
execution/calibration/protection/profile equivalence. Proper vendor DSP integration
is still required for OEM parity; no module hot switch or firmware write was done.
No nonzero tone or microphone capture; human listening remains unverified.

Also fixed a real host-oracle integrity defect:9Python assert checks disappeared
under-O. The historical optimized wrong-channel false positive was reproduced;
explicit requirements now reject wrong-channel/compiler-failure controls in both
modes, while32layout scenarios across two actual ALSA libraries pass. Host fixtures
remain synthetic controls, not additional hardware/DSP acceptance.

No kernel C/build/reboot, UCM profile/package input changes or automatic audio-service
restart hook.686 protected files/35aliases and user lock preferences unchanged;
raw mixer/PipeWire/kernel/pointer traces remain tablet-private. Prior camera/hang/DMA,
S5/full-image and actual vendor-quality audio requirements stay open.
