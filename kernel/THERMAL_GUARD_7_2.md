# MiPad2 thermal guard: remove delayed upward escalation

## Source defect and bounded fix

The prior case statement selected only the next state for each3s poll. Starting
cool while a sampled temperature is already>=80C produced states1,2,3, leaving
the appropriate1.33GHz ceiling unapplied for two further polls (nominal6s, not a
measured physical delay). At>=74C it similarly needed two polls from cool.

[Production Bash helper](../device_files/mipad2-thermal-guard) now selects the
required hot state in that same poll. Original thresholds67/74/80C and CPU
ceilings2.24/1.84/1.60/1.33GHz retained. Cooling remains one step at a time with
original61/68/74C hysteresis. Sampling still3s, original DTS/coretemp sensor
selection retained. Invalid input cannot replace the last state with empty text.
No policy designed to force a recording test pass or disable platform thermal
protection. No new kernel C patch, kernel build or reboot.

## Reproducible source and actual installed scope

Ten tests execute the extracted production Bash function: exact threshold edges,
512 seeded random cases against an independent policy oracle, direct hot jumps,
conservative cooling, hysteresis holds, invalid input, guarded state assignment,
unchanged ceiling constants/poll period and shell syntax. Full164 flash tests pass
normally and under Python-O. Test execution never touches host sysfs.

```sh
python3 -m unittest discover -s tests
python3 -O -m unittest discover -s tests
```

Actual7.2 r3 installation occurred only with no camera owner/client and below65C.
Normalized old installed code matched the audited original policy (comment-only
differences permitted), raw original bytes/mode/owner backed up root-private,
exact tested source syntax-checked and CAS/atomically replaced. Only thermalguard
service restarted; PID changed and stayed active through six cool-state samples
over18s, max53C, ceilings2.24GHz. Installed source SHA separately verified because
the guard is outside the historical686-file protection set; all686 unchanged.
Seven synthetic cases executed the installed helper without running its sysfs
loop or altering temperatures. **No real hot transition or thermal stabilization
has yet been measured with this source**, nor complete image/rootfs qualification.

Exact source/installation/scalar evidence: [summary](../tests/mipad2-thermal-guard-7.2-summary.json).
No raw logs/pointers/media exported; original backup remains tablet-private.
No user lock/audio settings changed or audible playback. UCM8 hashes match,
both sensors/ISP suspended, fresh kernel fault counts0 and no failed units.

An independent later normal rear63.841s/1917frame full-quality recording passed
before this fix was installed. That pass is not evidence that this thermal fix
caused smoother recording. Prior interrupted rear and3.5h hard-freeze root causes
remain unknown; failed-reset DMA quiescence and Android/OEM parity remain open.
