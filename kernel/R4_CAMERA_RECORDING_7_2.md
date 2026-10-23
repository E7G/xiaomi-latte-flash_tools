# 7.2 r4 camera/normal recording/resume regression

The already deployed image remains source69bb7d3f, release7.2.0-mipad2-integrated-r4;
these new commits add evidence and the exact strict-r4 native test fixture,
not a new production driver/image or reboot.

Two normal foreground full-quality 1080p H.264/stereo48k AAC app recordings:
front984 decoded frames/30.001831fps/max gap45.333ms, rear992 frames/30.011811fps/
max gap34.667ms. No gaps>50ms or adjacent exact decoded repeats. Per-process
GPU video-engine activity observed independently; exact encoder element identity
and every incoming source-frame conservation were not independently measured.
No diagnostic/background capture switches, raw media export or audible playback.

After normal recording, RTC12s added12321568us S0I3, actual codec PLL and both amps
ready after resume/digitalzero. Both cameras then passed four120frame native1080p
NV12 phases each: no sequence gaps/errors, expected observer EBUSY and owner
restart/reopen checks. Combined with pre-recording fixture:1920 native frames,
separate from1976 decoded app frames. No physical failed-reset DMA fault injection.

Deep original sensor geometry/controls/video format restored;2163 protected files
and35 private aliases unchanged;guards active/rescue default unchanged. Seven
superseded test caches removed only; recordings/logs/photos/kernels preserved.

Short-clips peaked75/78C. Acoustic/optical/rotation/mic quality, sustained thermal/
multi-hour hang, S5, idle audio power, factory DSP/MTP and full OEM parity remain
open. Quiet nonzero AAC noise is not microphone quality proof. Full OS image
not built. Raw UART/kernel/per-frame evidence stays tablet-private.

[Pinned report, method references, source fixture and scalar evidence](https://github.com/E7G/linux_latte/blob/7183298b4514d5881f653784320e3b43ea4fdd34/fix_file/MIPAD2_R4_CAMERA_RECORDING_7_2.md).
