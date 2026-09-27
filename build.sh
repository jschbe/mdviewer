#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Jochen Schmitt
# SPDX-License-Identifier: GPL-3.0-or-later

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: build.sh [-deb] [-i|-install] [-f|-force] [-h]

Clean old generated files in packaging/ and build a package (Arch by default).
Debug packages are disabled. By default (no parameters) only build is performed, no install.

  -deb         Build a Debian .deb package instead of an Arch package.
  -i, -install  Install after building: sudo pacman -U --needed for Arch,
               or sudo apt install with -deb (including missing dependencies).
               No installation without this option.
  -f, -force    Arch only: omit --needed to reinstall the same version.
               Has no effect with -deb.
  -h           Print this help and exit without building or installing.
EOF
}

install=false
force=false
deb=false
for argument in "$@"; do
    case "$argument" in
        -i|-install) install=true ;;
        -f|-force) force=true ;;
        -deb) deb=true ;;
        -h) usage; exit 0 ;;
        *) printf 'Unknown parameter: %s\n' "$argument" >&2; usage >&2; exit 1 ;;
    esac
done

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

builder=makepkg
if [[ "$deb" == true ]]; then
    builder=dpkg-deb
fi
for dependency in make python3 tar "$builder"; do
    if ! command -v "$dependency" >/dev/null 2>&1; then
        printf 'Required build tool not found: %s\n' "$dependency" >&2
        exit 1
    fi
done

if [[ "$deb" == true && "$install" == true ]] && ! command -v apt >/dev/null 2>&1; then
    printf 'Required installation tool not found: apt\n' >&2
    exit 1
fi

# Remove generated package files, keeping PKGBUILD and other source files.
shopt -s nullglob
rm -rf -- packaging/src packaging/pkg
old_files=(packaging/*.tar packaging/*.tar.* packaging/*.sig packaging/*.log packaging/*.deb)
if ((${#old_files[@]})); then
    rm -f -- "${old_files[@]}"
fi

make dist
version=$(python3 -c 'from mdview import __version__; print(__version__)')
if [[ "$deb" == true ]]; then
    make test
    package_root="$PWD/packaging/pkg/deb"
    package_file="$PWD/packaging/mdview_${version}-1_all.deb"
    make DESTDIR="$package_root" PREFIX=/usr install
    mkdir -p "$package_root/DEBIAN"
    chmod 755 "$package_root/DEBIAN"
    install -Dm644 LICENSE "$package_root/usr/share/doc/mdview/copyright"
    installed_size=$(du -sk "$package_root/usr" | cut -f1)
    cat > "$package_root/DEBIAN/control" <<EOF
Package: mdview
Version: ${version}-1
Section: text
Priority: optional
Architecture: all
Maintainer: Jochen Schmitt
Installed-Size: $installed_size
Depends: python3 (>= 3.10), python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-webkit-6.0, python3-markdown-it, python3-pygments
Description: Simple read-only Markdown viewer for GNOME
 View local Markdown and UTF-8 text files using GTK4, libadwaita and WebKitGTK.
EOF
    chmod 644 "$package_root/DEBIAN/control"
    dpkg-deb --root-owner-group --build "$package_root" "$package_file"
    if [[ "$install" == true ]]; then
        sudo apt install "$package_file"
    fi
    exit 0
fi

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
