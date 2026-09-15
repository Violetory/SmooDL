#!/bin/sh
set -eu

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "Usage: shortcuts/build.sh https://download.example.com [--hubsign|--unsigned]" >&2
    exit 64
fi

signer=apple
if [ "$#" -eq 2 ]; then
    case "$2" in
        --hubsign) signer=hubsign ;;
        --unsigned) signer=none ;;
        *) echo "Unknown option: $2" >&2; exit 64 ;;
    esac
fi

base_url=${1%/}
case "$base_url" in
    https://*) ;;
    http://127.0.0.1:*|http://localhost:*) ;;
    *)
        echo "Base URL must use HTTPS (localhost HTTP is allowed for development)." >&2
        exit 64
        ;;
esac
# An origin is embedded in source code. Reject paths, credentials, query strings
# and source-language metacharacters instead of trying to escape arbitrary URLs.
if ! printf '%s\n' "$base_url" | LC_ALL=C grep -Eq '^https?://[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:[0-9]{1,5})?$'; then
    echo "Base URL must be an origin containing only a hostname and optional port." >&2
    exit 64
fi

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_file="$project_dir/shortcuts/SmooDL.cherri"
output_dir="$project_dir/shortcuts/dist"
compiler_version=v2.3.0
compiler_sha256=15e4651d4c957a03cdfeb6c5fd74ea8ac66f1d6e20897883fef3547fdd36d264
compiler_cache="${TMPDIR:-/tmp}/smoodl-cherri-$compiler_version"
compiler="$compiler_cache/cherri"

mkdir -p "$compiler_cache" "$output_dir"

if [ ! -x "$compiler" ]; then
    archive="$compiler_cache/cherri.zip"
    curl -fsSL \
        "https://github.com/electrikmilk/cherri/releases/download/$compiler_version/cherri_darwin-arm64.zip" \
        -o "$archive"
    actual_sha256=$(shasum -a 256 "$archive" | awk '{print $1}')
    if [ "$actual_sha256" != "$compiler_sha256" ]; then
        echo "Cherri checksum mismatch." >&2
        exit 65
    fi
    unzip -qo "$archive" -d "$compiler_cache"
    chmod +x "$compiler"
fi

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/smoodl-shortcut-build.XXXXXX")
temporary_source="$build_dir/SmooDL.cherri"
unsigned_shortcut="$build_dir/SmooDL_unsigned.shortcut"
signed_shortcut="$output_dir/SmooDL.shortcut"
trap 'rm -rf "$build_dir"' EXIT HUP INT TERM

escaped_base_url=$(printf '%s' "$base_url" | sed 's/[&|]/\\&/g')
sed "s|__SMOODL_BASE_URL__|$escaped_base_url|g" "$source_file" > "$temporary_source"

"$compiler" "$temporary_source" --skip-sign --no-ansi
python3 "$project_dir/shortcuts/validate.py" "$unsigned_shortcut"

if [ "$signer" = hubsign ]; then
    signed_temporary="$build_dir/SmooDL-hubsign.shortcut"
    "$compiler" "$temporary_source" \
        --hubsign \
        --share=anyone \
        --output="$signed_temporary" \
        --no-ansi
    mv "$signed_temporary" "$signed_shortcut"
    echo "Built $signed_shortcut with HubSign"
    exit 0
fi

if [ "$signer" = none ]; then
    cp "$unsigned_shortcut" "$output_dir/SmooDL_unsigned.shortcut"
    echo "Built unsigned validation artifact: $output_dir/SmooDL_unsigned.shortcut"
    exit 0
fi

attempt=1
while :; do
    signing_input="$build_dir/SmooDL-signing-$attempt.shortcut"
    signed_temporary="$build_dir/SmooDL-signed-$attempt.shortcut"
    cp "$unsigned_shortcut" "$signing_input"
    if shortcuts sign \
        --mode anyone \
        --input "$signing_input" \
        --output "$signed_temporary"; then
        break
    fi
    if [ "$attempt" -ge 5 ]; then
        echo "Apple shortcut signing failed after $attempt attempts." >&2
        exit 69
    fi
    attempt=$((attempt + 1))
    echo "Apple shortcut signing failed; retrying ($attempt/5)..." >&2
    sleep 2
done

mv "$signed_temporary" "$signed_shortcut"
echo "Built $signed_shortcut"
