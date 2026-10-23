# 7.2 physical AIF2 speaker graph candidate (not deployed)

Real r4 read-only DAPM witness shows inactive PCM/DAI streams but an active cycle:
AIF1 Playback -> DAC_REF -> AIF2 Capture -> synthetic C2C capture -> AIF1 Playback.
Current core reverses CPU direction for C2C and treats a walking cycle as connected.
This is a board-topology issue, not a generic-core patch or cache-replay problem.

Candidate replaces the fake internal bridge and dummy amp links with the physical
rt5659-aif2 TX -> both TFA receiver C2C link. Fixed48kS16 stereo; amps clock consumers,
SSP/AIF1S24 and permanent PLL dependencies preserved. Factory digital-mute now obeys
default deferred safe-probe because real C2C calls mute on power-down too.

Machine and3-object factory external modules W1/Clang21/thinLTO/modpost pass without
warnings; r4 build hashes preserved, neither module installed/loaded.18positive
host runs(normal/-O) plus4precise prior-source negative controls pass. Fixtures use
actual endpoint-walk/direction/C2C parameter code, but are not hardware power proof.

The tablet STILL runs unchangedr4. Full candidate image, boot/runtime clock gating,
zeroPCM/reopen/mic-only/duplex/PM/headphone/acoustic/power testing remain required.
Correct future gates require idle clocks/amps OFF, active audio READY, then OFF;
do not enforce old r4 idle-on expectations. Factory remains unselected; firmware/
UCM/MTP/full alternative configuration and hardware lifecycle are unqualified.
No audible test, power saving measurement, new kernel or runtime graph repair
was applied in this candidate follow-up. Broad OEM-equivalence work remains open.

[Pinned source, actual graph witness, references and regression details](https://github.com/E7G/linux_latte/blob/8bc6bf83ae3f3104a5649036c013bac4a0155bdd/fix_file/MIPAD2_AIF2_IDLE_GRAPH_7_2.md).
