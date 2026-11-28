#!/usr/bin/env bash
# Boot only the downloaded package and a private diagnostic initramfs; no physical disk.
set -euo pipefail
export LC_ALL=C
umask 077
manifest=$(realpath -e -- "$1")
source=$2
sha=$3
out=$(realpath -e -- "$4")
test -z "$(find "$out" -mindepth 1 -maxdepth 1 -print -quit)"
scripts=$(cd -- "$(dirname -- "$0")" && pwd)
scratch=$(mktemp -d "$out/fixture.XXXXXXXX")
trap 'rc=$?; printf "%s\n" "$rc" > "$out/exit-status"; exit "$rc"' EXIT
tree="$scratch/tree"
python3 -B "$scripts/prepare_r32_package_vm.py" "$manifest" "$source" "$sha" "$tree" |
    tee "$out/input.txt"

root="$tree/guest"
cd -- "$scratch"
mkdir -p "$root"/{usr/bin,proc,sys,dev}
install -m0755 "$(command -v busybox)" "$root/usr/bin/busybox"
kmod=$(command -v kmod)
install -m0755 "$kmod" "$root/usr/bin/kmod"
for n in depmod insmod modprobe; do ln -s kmod "$root/usr/bin/$n"; done
ldd "$kmod" > "$out/runtime-libraries.txt"
if grep -Fq 'not found' "$out/runtime-libraries.txt"; then exit 10; fi
mapfile -t libs < <(awk '$2 == "=>" && $3 ~ /^\//{print $3} $1 ~ /^\//{print $1}' "$out/runtime-libraries.txt")
test "${#libs[@]}" -gt 0
cp -L --parents -- "${libs[@]}" "$root"
mkdir -p -- "$root/lib"
ln -s ../usr/lib/modules "$root/lib/modules"

cat > "$root/init" <<'GUEST'
#!/usr/bin/busybox sh
set -eu
bb=/usr/bin/busybox
trap 'rc=$?; echo "R32_FAILURE=$rc"; "$bb" poweroff -f' EXIT
"$bb" mount -t proc proc /proc
"$bb" mount -t sysfs sysfs /sys
"$bb" mount -t devtmpfs devtmpfs /dev
release=$("$bb" uname -r)
test "$release" = 7.2.15-mipad2-integrated-r32
test "$("$bb" cat /sys/module/module/parameters/sig_enforce)" = Y
echo "R32_KERNEL=$release"
trace=/sys/kernel/tracing
"$bb" mount -t tracefs tracefs "$trace"
event=events/pmc_atom/pmc_atom_s2idle
test "$("$bb" cat "$trace/$event/enable")" = 0
for col in func_dis func_dis_2 d3_sts_0 d3_sts_1 pss forced_clks; do
    "$bb" grep -Eq "field:[^;]*[[:space:]]$col;.*size:4;.*signed:0;" "$trace/$event/format"
done
echo R32_PMC_DEFAULT_OFF=1
if /usr/bin/insmod /unsigned-erofs.ko >/unsigned-message 2>&1; then
    echo R32_UNSIGNED_UNEXPECTEDLY_LOADED=1
    exit 13
fi
"$bb" cat /unsigned-message
"$bb" grep -Eq 'Required key not available|Key was rejected by service' /unsigned-message
echo R32_UNSIGNED_REJECTED=1
/usr/bin/depmod -a "$release"
for n in erofs intel-chtwc-adc intel_pmic_chtwc_thermal nft_nat nft_masq nft_chain_nat \
         ov5693 t4ka3 atomisp dw9719 snd_soc_rt5659; do
    echo "R32_LOADING=$n"
    /usr/bin/modprobe "$n"
    registered=$("$bb" printf '%s' "$n" | "$bb" tr '-' '_')
    "$bb" grep -q "^$registered " /proc/modules
done
echo R32_SIGNED_MODULE_LOADS=11
echo R32_VM_PASS=1
trap - EXIT
exec "$bb" poweroff -f
GUEST
chmod 0755 "$root/init"
(cd "$root"; find . -print0 | sort -z | cpio --quiet -o --null -H newc --owner=0:0 | gzip -1) > initrd

cat > grub.cfg <<'GRUB'
insmod serial
serial --unit=0 --speed=115200
terminal_input serial
terminal_output serial
search --no-floppy --file --set=root /r32-package-fixture
set timeout=0
menuentry 'Mi Pad 2 R32 package smoke (no live disk)' {
    echo R32_UEFI_GRUB_SELECTED=1
    linux /vmlinuz console=ttyS0,115200 module.sig_enforce=1 panic=-1 loglevel=5
    initrd /initrd
}
GRUB
grub-script-check grub.cfg
grub-mkstandalone -O x86_64-efi --locales= --fonts= --themes= \
    --modules='normal part_gpt fat linux serial search_fs_file' \
    -o BOOTX64.EFI "boot/grub/grub.cfg=$scratch/grub.cfg"
truncate -s 128M esp.fat
mkfs.fat -F32 -n LATTER32 esp.fat
mmd -i esp.fat ::EFI ::EFI/BOOT
mcopy -i esp.fat BOOTX64.EFI ::EFI/BOOT/BOOTX64.EFI
printf 'r32 package fixture\n' > r32-package-fixture
mcopy -i esp.fat "$tree/vmlinuz" initrd r32-package-fixture ::
truncate -s 132M vm.raw
sgdisk --clear --new=1:2048:+128M --typecode=1:ef00 vm.raw > "$out/gpt.txt"
dd if=esp.fat of=vm.raw bs=1M seek=1 conv=notrunc status=none
cp /usr/share/OVMF/OVMF_VARS_4M.fd vars.fd
timeout 155s qemu-system-x86_64 \
    -machine q35,accel=tcg -cpu Westmere,family=6,model=76,stepping=3,movbe=on,rdrand=on \
    -smp 2 -m 1408 -nodefaults -display none -vga none -serial stdio -monitor none -nic none -no-reboot \
    -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
    -drive if=pflash,format=raw,file=vars.fd -drive if=ide,index=0,format=raw,file=vm.raw \
    < /dev/null > "$out/guest.serial.log" 2>&1
sed -E $'s/\x1b\\[[0-?]*[ -/]*[@-~]//g' "$out/guest.serial.log" | tr -d '\r' > "$out/guest.clean.log"
for entry in R32_UEFI_GRUB_SELECTED=1 R32_KERNEL=7.2.15-mipad2-integrated-r32 \
    R32_PMC_DEFAULT_OFF=1 R32_UNSIGNED_REJECTED=1 R32_SIGNED_MODULE_LOADS=11 R32_VM_PASS=1; do
    grep -Fxq "$entry" "$out/guest.clean.log"
done
if grep -Eq 'R32_(FAILURE|UNSIGNED_UNEXPECTEDLY_LOADED)=' "$out/guest.clean.log"; then exit 18; fi
printf 'PASS: exact R32 ALPM image booted through isolated UEFI; unsigned control rejected\n' | tee "$out/result.txt"
