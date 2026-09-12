# Secure Boot shim source

`shimx64.efi` is Ubuntu shim 15.8's Microsoft-signed x86_64 binary.  This
generation uses the Microsoft UEFI CA 2011 trust chain required by the Mi Pad
2's original firmware.  It must not be re-signed by the image build.

Source package:

`https://mirror.comp.nus.edu.sg/ubuntu/pool/main/s/shim-signed/shim-signed_1.59+15.8-0ubuntu2_amd64.deb`

Pinned hashes:

```text
f8ed71ce2d91a304b6d5eb84997f846f331b554578bc02dbfe78e13ad8ac81a9  shim-signed_1.59+15.8-0ubuntu2_amd64.deb
4c89145e958cf592a6f16552eadf112ef2c1c525e2435c2761e6a99fa88188b3  shimx64.efi
5f9fc41db3dfe3b581fc20cae696af82c5ca21e96071ec9c4c28ee4a15f989d8  mmx64.efi
```

Boot chain:

```text
UEFI firmware -> BOOTX64.EFI (Microsoft-signed shim)
              -> grubx64.efi (original project MOK)
              -> vmlinuz (original project MOK)
```
