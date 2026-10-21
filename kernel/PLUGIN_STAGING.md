> Opt-in source camera rootfs merge is now wired to build_rootfs.sh with pre-NBD hash validation and mandatory native loader checks: [usage and exact qualification limits](CAMERA_ROOTFS.md). Default builds do not promote this candidate.

> Optional complete source-app/four-plugin candidate composition is now available via scripts/stage_camera_app.py: [requirements, isolation and unqualified foreground gate](SOURCE_APPLICATION.md). No automatic rootfs merge, flash or default promotion.

> Optional source-built AAC can now be staged with an independently pinned receipt: [current four-plugin source requirements and tests](SOURCE_AAC.md). Default three-plugin mode below is unchanged. App/launcher/image integration remains pending.

# Manual functional camera-plugin package staging

Candidate-only; no rootfs/default/launcher installation is triggered.

`scripts/stage_camera_plugins.py` accepts the NEW pinned Snapshot source builder's
completed three-plugin output. It requires an explicit SHA-256 of `receipt.json`
and independently verifies exact1.28.7 development ABI, component set, regular
files, bytes/hashes, x86-64 ELF, absent RPATH/RUNPATH and dependency-name manifest
before creating a NEW package root. Source and package roots must differ; no
existing package directory is overwritten. All checks also run in `--dry-run`.

```sh
python3 scripts/stage_camera_plugins.py \
  /absolute/path/to/verified-source-build /absolute/path/to/new-package-root \
  --receipt-sha256 EXPLICIT_64_CHARACTER_SHA256 --dry-run
```

Remove `--dry-run` to stage. The build receipt must first be obtained from a
trusted, explicitly pinned source build; this stager is an integrity/shape check,
not independent proof that arbitrary binaries were built by that source. It
does not execute the plugins. Python3 plus GNU readelf are required.

Payload is only three executable plugin files under
`usr/local/lib/mipad2-gst-functional/<recipe-sha256>/plugin/` and a readable
`usr/share/doc/mipad2-gst-functional/manifest.json`. No Snapshot, AAC, desktop
launcher, diagnostic tracer, environment override or system-library replacement
is staged. The output is a package tree, not an automatically bootable image.

Nine host contracts pass normally and with Python `-O`. The actual corrected
source-built encoding/videofilter/VA plugins were staged successfully, with exact
build receipt SHA `fcd17ec7505804f81c764976dc335094633cb7265d47684550f2acb7ec03b1b2`.
The manifest is retained in `kernel/tests/camera-plugin-staging-evidence.json`.
Device recording evidence applies to those same binary hashes installed in an
isolated candidate directory, not to a completed flash image or this package
tree's exact destination path being flashed/tested.

The matching private SDK, RPATH export fix and scoped dual-camera recording
evidence are in [the pinned Snapshot checkpoint](https://github.com/E7G/snapshot/blob/8266d3d5a523351dc7737e8ed851469db98acbab/MIPAD2_PORTABLE_PLUGIN_DEVICE.md).
Continue full application/AAC/launcher packaging and photo/reopen/resume/cold-boot/
foreground qualification before opt-in rootfs integration. Original stable
launcher, recovery and kernel remain unchanged.
