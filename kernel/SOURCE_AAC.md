# Optional source AAC payload extension

Default `stage_camera_plugins.py` behavior remains the original three functional
plugins. Supplying BOTH `--aac-root` and `--aac-receipt-sha256` additionally stages
one source-built AAC/libav plugin. No app/launcher/rootfs installation is implied.

Pinned source builder and current device checkpoint:
[E7G/Snapshot 0a7ce87](https://github.com/E7G/snapshot/tree/0a7ce87affa902f33599819aed5c4123a548f1c6/contrib/mipad2/portable-plugins).
AAC uses official gst-libav1.28.7 and exact GStreamer1.28.7 plus matching FFmpeg9.0.1
development inputs. The private header/link SDK is NOT deployed; the source plugin
uses the target's original full system FFmpeg9.0.1 shared libraries.

```sh
python3 scripts/stage_camera_plugins.py \
  /absolute/functional-build /absolute/new-four-plugin-package \
  --receipt-sha256 EXPLICIT_FUNCTIONAL_RECEIPT_SHA256 \
  --aac-root /absolute/source-aac-build \
  --aac-receipt-sha256 EXPLICIT_AAC_RECEIPT_SHA256 --dry-run
```

Remove `--dry-run` to stage. Both receipts must come from trusted, explicitly
pinned source builds; these integrity checks do not independently attest arbitrary
input binaries. AAC receipt state/version/recipe hash/codec+format63.1.101,
filter12.1.101/util61.1.101/GStreamer ABI/file sizes/hashes/x86-64 ELF/absent RPATH
and dependency manifest are checked BEFORE the first package output write.
Missing one option, wrong ABI, changed file or symlinked root is rejected.

AAC is staged under
`usr/local/lib/mipad2-gst-aac-source/<aac-recipe-sha256>/plugin/libgstlibav.so`;
the original three functional plugins retain their own versioned directory.
One common provenance manifest declares AAC included, app/launcher excluded and
SDK libraries not deployed. No replacement of `/usr/lib`, no loader/environment
override, and no source app/desktop integration is performed.

14 stager contracts pass normally/`-O` (nine existing + five AAC). Full unittest
discovery22cases passes normally/`-O`; the older standalone kernel preflight is a
separate test. Actual four-plugin output is staged and recorded in
`kernel/tests/source-aac-staging-evidence.json`; the AAC build receipt SHA is
`910ee6fd79a00acdf7aa5ce168793ba1a4f0ac318064c7d520b6819c25984335`.

The same source plugin hashes passed target relocation/loading, synthetic AAC
encoding/decode and a fresh front→rear full-quality1080p recording process.
Both saved clips are approximately30fps, with maximum PTS gaps36/34ms and no
intervals>50ms. Original temporary AAC is absent from that test process's maps.
This is scoped recording evidence, not full foreground/optics/Android parity.

The staged package tree's precise destination layout has NOT been flashed as a
complete image. Snapshot app+launcher source packaging and qualification of
photos, repeated openings, resume, foreground preview, S5 cold boot and broad
hardware remain open. Stable defaults and the pre-existing camera AF work are
preserved. See [the complete scoped checkpoint](https://github.com/E7G/snapshot/blob/0a7ce87affa902f33599819aed5c4123a548f1c6/MIPAD2_SOURCE_AAC_DEVICE.md).
