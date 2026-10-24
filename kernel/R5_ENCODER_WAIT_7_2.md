# r5 encoded recording: waits localized, not fixed

Three full-quality foreground diagnostic windows still fail cadence. Kernel
trace shows completed buffers waiting a median102.414ms before DQ; native
offsets remain consecutive. Actual VA H.264 encoder sink chain median32.949ms;
preview queue is not directly blocking. 730 in-window native PTS/offset pairs
reach encoder input, but complete sensor-to-MP4 conservation remains unproved.

Private forwarding measurements: vaEndPicture738calls, wall19.056s versus CPU
3.163s. Actual driver is IRQL2.4.5, not generic Intel2.4.1. Pinned matching-tag
source contains CBR/VBR synchronous post-pack checks; actual BRC iteration/GPU
wait attribution is not measured yet. No rate/quality reduction or claimed fix.
All raw traces/media remain device-private; source/driver/default unchanged,
no reboot/nonzero playback. Final files/aliases/settings/control/PM audit passes.

[Pinned kernel report and qualification limits](https://github.com/E7G/linux_latte/blob/6230a483f8d88d27780347806053198950719d94/fix_file/MIPAD2_R5_ENCODER_WAIT_7_2.md).
