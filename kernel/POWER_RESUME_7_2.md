# 7.2 r3 actual system resume and native camera checks

Pinned kernel integration evidence: [two actual system s2idle/S0I3 returns and
post-resume native cameras](https://github.com/E7G/linux_latte/blob/d0d9224cfbe8b7afba38b81aa84d86e8e61f7379/fix_file/MIPAD2_7_2_PM_RESUME.md).

Two requested12s RTC suspends completed on the same7.2 r3 boot, PMC S0I3 increases
12.020448s/11.590176s and OS estimated suspended11.461734s/11.038792s. Different
measurement windows remain explicit; no rewritten/calibrated timing. Both units
exit0, RTCalarmsclear, no new kernel fault markers. Shared IRQ9acpi/INT0002 is
not uniquely RTC; second fixed ACPI RTCevent counter incremented once.

After EACH return, both native1920x1080NV12 cameras passed four120-frame owner
restart/reopen phases plus nonowner rejection:1920frames/64negative operations
total, no sequence gaps/errors, worst interval34.098ms. Formats, sensor crop and
controls restored with readback; sensors/ISP runtime-suspended usage0 after each.
Raw buffer capture is NOT encoded video, optics, live-preview or acoustics.

No kernel C/build/reboot, new thermal policy, image/package installation, media
deletion or audible playback. Prior installed immediate thermal escalation source
still matches separately;686 protected files and35 private aliases unchanged.
Compositor API responds, internal DSI connected/backlighton; visual content not
human verified. Automatic lock/DPMS/suspend remainOFF per local user preference.

First serial reader was live/marker-proven, later explicitly closed; raw trace
stored only tablet-private/root0600. Second had no reader, but USB still attached;
neither is pristine untethered battery-drain/long-sleep evidence. Host10scalar
oracles normally/-O plus existing raw fixture and four other host suites pass,
not additional physical or DMA-failure coverage. Full source/scalars in link above.

3.5h hard-freeze root cause, failed-reset DMA fencing, optics/audio/headphones/mic,
S5 and full image/rootfs ABI/ownership/OEM parity remain open. No default promotion.
