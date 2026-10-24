# MiPad2 7.2 r5 deployed: physical AIF2 speaker graph

Image source `8bc6bf83ae3f3104a5649036c013bac4a0155bdd`; exact r4 stock-backend
config. Complete bzImage/31 module build, CMS signatures, ALPM query/preflight
pass. Three pre-existing LTO stack warnings retained. Not installed via pacman.
Exactly one guarded warm reboot; rescue default unchanged, no S5 claim.

Read-only hardware tests show idle PLL/I2S/amps off; zero playback powers ready
amps; stop returns off. Mic-only keeps its capture PLL on but speaker AIF2/amps
off. Duplex powers speakers; speaker stop with mic still active powers them
down again. No route overlays, register/cache replay, DSP or MTP programming.
Mic samples discarded without saving; no nonzero playback/acoustic test.

Two independent 12-second RTC cycles on the same boot: S0I3 12088000 and
12176896 us, correct before/after/active/settled clock states, zero trace overruns
or new faults. USB attached/shared IRQ9: not pristine untethered power proof.

Both cameras passed four 120-frame phases each at 1920x1080 NV12 (960 frames),
no sequence discontinuities/buffer errors, plus four default frames per camera
after the second resume. Native stream restart/close/reopen/EBUSY tests, not
encoded app recording or optical qualification. Formats/controls restored,
sensors/ISP suspended. Final 2214 protected files and 48 current manifest payload
files verified unchanged, 35 private aliases preserved, all jobs terminal.

Factory DSP stays unselected; fresh acoustics/headset, r5 normal encoded app
recording, S5/long-run/physical failed-reset DMA and OEM parity remain open.
Raw media/logs remain device-private. Auto-lock/DPMS/auto-suspend remain off;
thermal/no-idle guards active. Full OS image not built.

[Pinned kernel report, scalar hashes and limitations](https://github.com/E7G/linux_latte/blob/08b48331b802b27040852efb18a753ab2af3e8d8/fix_file/MIPAD2_R5_DEPLOYMENT_7_2.md).
