#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: build.sh [-i|-install] [-f|-force] [-h]

Clean old generated files in packaging/ and build the Arch package.
Debug packages are disabled. By default (no parameters) only build is performed, no install.

  -i, -install  Install after building using sudo pacman -U --needed.
               Skip installation if the same version is already installed.
  -f, -force    Omit --needed to allow reinstalling the same version.
               Only affects installation; requires -i or -install to install.
  -h           Print this help and exit without building or installing.
EOF
}

install=false
force=false
for argument in "$@"; do
    case "$argument" in
        -i|-install) install=true ;;
        -f|-force) force=true ;;
        -h) usage; exit 0 ;;
        *) printf 'Unknown parameter: %s\n' "$argument" >&2; usage >&2; exit 1 ;;
    esac
done

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

# Remove generated makepkg files, keeping PKGBUILD and other source files.
shopt -s nullglob
rm -rf -- packaging/src packaging/pkg
old_files=(packaging/*.tar packaging/*.tar.* packaging/*.sig packaging/*.log)
if ((${#old_files[@]})); then
    rm -f -- "${old_files[@]}"
fi

make dist
version=$(python3 -c 'from mdview import __version__; print(__version__)')
cp -- "dist/mdview-${version}.tar.gz" packaging/
cd packaging
makepkg -f

if [[ "$install" == true ]]; then
    # PKGBUILD disables debug packages; use makepkg's configured output path.
    package_list=$(makepkg --packagelist)
    mapfile -t packages <<< "$package_list"
    pacman_options=(-U)
    if [[ "$force" == false ]]; then
        pacman_options+=(--needed)
    fi
    sudo pacman "${pacman_options[@]}" "${packages[@]}"
fi
