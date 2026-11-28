#!/usr/bin/env bash
# Fetch the exact Windows Platform-Tools used to qualify the Mi Pad 2 image.
set -euo pipefail

version=37.0.3
url="https://dl.google.com/android/repository/platform-tools_r${version}-win.zip"
sha256=89d108360a3bf2924d3bea837239edaccc22fd6ff5befd3787c4348a9fe4f09d

die() { printf '%s\n' "$*" >&2; exit 1; }
verify() {
    [[ -f "$1" && ! -L "$1" ]] || die 'Platform-Tools input must be a regular archive'
    local actual
    actual=$(sha256sum < "$1")
    [[ "$actual" == "$sha256  -" ]] || die 'Windows Platform-Tools SHA-256 mismatch'
}

case "${1:-}" in
    --print-pin)
        [[ $# == 1 ]] || die 'Too many arguments for --print-pin'
        printf 'version=%s\nurl=%s\nsha256=%s\n' "$version" "$url" "$sha256"
        exit
        ;;
    --verify)
        [[ $# == 2 ]] || die 'Expected --verify ARCHIVE'
        verify "$2"
        exit
        ;;
    --fetch)
        [[ $# == 2 ]] || die 'Expected --fetch ARCHIVE'
        ;;
    *)
        die 'Expected --print-pin, --verify ARCHIVE, or --fetch ARCHIVE'
        ;;
esac

archive=$2
if [[ -e "$archive" || -L "$archive" ]]; then
    # Never overwrite or silently fall back from an unexpected cached input.
    verify "$archive"
    exit
fi
mkdir -p -- "$(dirname -- "$archive")"
scratch=$(mktemp -- "$archive.part.XXXXXXXX")
trap 'rm -f -- "$scratch"' EXIT
curl --disable --fail --show-error --silent --location --proto '=https' \
    --proto-redir '=https' --connect-timeout 20 --max-time 180 --retry 3 \
    --output "$scratch" "$url"
verify "$scratch"
# Link atomically into place; another writer must not be overwritten.
ln -T -- "$scratch" "$archive"
