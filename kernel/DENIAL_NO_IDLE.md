# Existing no-idle service: Denial compatibility

The system inhibitor alone does not control Denial's own DPMS timer. An active
`mipad2-test-no-idle.service` and disabled GNOME idle settings therefore did not
prove that this desktop would keep its display on.

The kernel integration branch now fixes the existing helper, rather than adding
a second service or input-injection watchdog. Use kernel source commit
`7b7a30c592c8f7313b6c721ccd2fd4aad690d070` or a descendant when staging these
support sources. `stage_kernel_support.py` also installs its Python backend at
`/usr/local/libexec/mp2-test-no-idle-denial`. The image package list already
includes Python. The standalone no-idle package now explicitly depends on it.

The commands remain:

```sh
sudo mp2-test-no-idle enable
sudo mp2-test-no-idle status
sudo mp2-test-no-idle disable
```

When Denial is present, the backend uses its native versioned settings API,
changes only `power.idleDpmsEnabled`, and retains the original boolean in a
private user-owned restore record. Repeated enable does not overwrite that
record. Disable restores only the owned setting, keeping unrelated intervening
user changes; stale revisions/errors fail visibly and retain recovery data.
If a restore record exists but Denial is unavailable, restoration waits for the
session instead of overwriting its settings file offline. Native status failure
prevents a misleading GNOME-only PASS. Authentication, automatic lock, power-key
action and Denial suspend policy remain unchanged.

Evidence, 2026-10-22:

- 18 Denial/backend/shell-integration cases pass normally and under Python `-O`.
  These include native failure blocking the old false PASS, enable failure not
  claiming success, and restore failure retaining the existing inhibitor.
- Legacy GNOME shell tests and all 87 flash-tool tests pass, normally and under
  `-O` where applicable. These are host fixtures, not live lock/restore tests.
- The exact backend source passes a read-only status call against the real
  Denial socket; it reports native automatic DPMS disabled, with no setting write.
- The user's requested device setting was separately changed and persisted
  through the native API, then observed powered on over 630 seconds. It was
  still disabled after the subsequent reboot into stable bqdiag1.
- The new helper itself has **not** replaced the installed tablet helper, and
  its live enable/disable cycle has not been performed. No kernel rebuild,
  reboot, complete image build or new service was needed for this source change.

The current native `audio.get` read-only call returns error `locked`, confirming
that the desktop session is presently locked. This is evidence about a camera
foreground test prerequisite, not a new camera driver failure or evidence about
the previous r26 session. Do not bypass Snapshot's foreground gate or disable
authentication as a camera fix.

Upstream interface and schema:
[Denial control protocol](https://github.com/denialwm/denial/blob/fee449dfcbfce7b994ba1bd8930f57751494a9e5/docs/protocol/control-v1.md),
[power settings](https://github.com/denialwm/denial/blob/fee449dfcbfce7b994ba1bd8930f57751494a9e5/dart_shell/lib/src/settings/shell_settings.dart).
