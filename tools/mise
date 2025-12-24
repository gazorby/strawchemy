#!/usr/bin/env bash
set -eu

__mise_bootstrap() {
    local cache_home="${XDG_CACHE_HOME:-$HOME/.cache}/mise"
    export MISE_INSTALL_PATH="$cache_home/mise-2025.12.12"
    install() {
        local initial_working_dir="$PWD"
        #!/bin/sh
        set -eu

        #region logging setup
        if [ "${MISE_DEBUG-}" = "true" ] || [ "${MISE_DEBUG-}" = "1" ]; then
          debug() {
            echo "$@" >&2
          }
        else
          debug() {
            :
          }
        fi

        if [ "${MISE_QUIET-}" = "1" ] || [ "${MISE_QUIET-}" = "true" ]; then
          info() {
            :
          }
        else
          info() {
            echo "$@" >&2
          }
        fi

        error() {
          echo "$@" >&2
          exit 1
        }
        #endregion

        #region environment setup
        get_os() {
          os="$(uname -s)"
          if [ "$os" = Darwin ]; then
            echo "macos"
          elif [ "$os" = Linux ]; then
            echo "linux"
          else
            error "unsupported OS: $os"
          fi
        }

        get_arch() {
          musl=""
          if type ldd >/dev/null 2>/dev/null; then
            if [ "${MISE_INSTALL_MUSL-}" = "1" ] || [ "${MISE_INSTALL_MUSL-}" = "true" ]; then
              musl="-musl"
            elif [ "$(uname -o)" = "Android" ]; then
              # Android (Termux) always uses musl
              musl="-musl"
            else
              libc=$(ldd /bin/ls | grep 'musl' | head -1 | cut -d ' ' -f1)
              if [ -n "$libc" ]; then
                musl="-musl"
              fi
            fi
          fi
          arch="$(uname -m)"
          if [ "$arch" = x86_64 ]; then
            echo "x64$musl"
          elif [ "$arch" = aarch64 ] || [ "$arch" = arm64 ]; then
            echo "arm64$musl"
          elif [ "$arch" = armv7l ]; then
            echo "armv7$musl"
          else
            error "unsupported architecture: $arch"
          fi
        }

        get_ext() {
          if [ -n "${MISE_INSTALL_EXT:-}" ]; then
            echo "$MISE_INSTALL_EXT"
          elif [ -n "${MISE_VERSION:-}" ] && echo "$MISE_VERSION" | grep -q '^v2024'; then
            # 2024 versions don't have zstd tarballs
            echo "tar.gz"
          elif tar_supports_zstd; then
            echo "tar.zst"
          elif command -v zstd >/dev/null 2>&1; then
            echo "tar.zst"
          else
            echo "tar.gz"
          fi
        }

        tar_supports_zstd() {
          # tar is bsdtar or version is >= 1.31
          if tar --version | grep -q 'bsdtar' && command -v zstd >/dev/null 2>&1; then
            true
          elif tar --version | grep -q '1\.(3[1-9]|[4-9][0-9]'; then
            true
          else
            false
          fi
        }

        shasum_bin() {
          if command -v shasum >/dev/null 2>&1; then
            echo "shasum"
          elif command -v sha256sum >/dev/null 2>&1; then
            echo "sha256sum"
          else
            error "mise install requires shasum or sha256sum but neither is installed. Aborting."
          fi
        }

        get_checksum() {
          version=$1
          os=$2
          arch=$3
          ext=$4
          url="https://github.com/jdx/mise/releases/download/v${version}/SHASUMS256.txt"

          # For current version use static checksum otherwise
          # use checksum from releases
          if [ "$version" = "v2025.12.12" ]; then
            checksum_linux_x86_64="ccf5f0bac2f0dd56682827337d9cf3141ea4ca3d58da1fc0a1946a6d2ebbf729  ./mise-v2025.12.12-linux-x64.tar.gz"
            checksum_linux_x86_64_musl="f4bac31b7317690f421184b10fb7920ae43d71316889b0df8a7a10fbb3e0b844  ./mise-v2025.12.12-linux-x64-musl.tar.gz"
            checksum_linux_arm64="72dae36b4c7a01e07dc73566748e364e47dabeeb1563c91578abfb73a791f8c0  ./mise-v2025.12.12-linux-arm64.tar.gz"
            checksum_linux_arm64_musl="8875845eaf270e174d63c41c1fe629d893b7cc78bc9be494b2f81f8f1b98217b  ./mise-v2025.12.12-linux-arm64-musl.tar.gz"
            checksum_linux_armv7="1c472577b500cd273d3e5c1f9251405d820e6168446da51ba76eadd7ac86efe1  ./mise-v2025.12.12-linux-armv7.tar.gz"
            checksum_linux_armv7_musl="4135f70dd3b4ec7ba8a23499c414ee4e27ca6cd5def1212f144a70dfaa23ccc7  ./mise-v2025.12.12-linux-armv7-musl.tar.gz"
            checksum_macos_x86_64="96eb9e0c05eda0dd2520bd56425c0202c889c947badfe8e9eff54a5eec71ee61  ./mise-v2025.12.12-macos-x64.tar.gz"
            checksum_macos_arm64="2a44dad05d75a2d2539aa6b5b57f9a6dc68937a359efbd312dd6a12997d6df84  ./mise-v2025.12.12-macos-arm64.tar.gz"
            checksum_linux_x86_64_zstd="ac693019c8971036061a0c2b164d51ceea03df8cab3f3b45c3baad5fe0b7446d  ./mise-v2025.12.12-linux-x64.tar.zst"
            checksum_linux_x86_64_musl_zstd="fcec621c9b4d9c27adf43ec7dfc70691816d34da43f443e4d8866a2947ecfda4  ./mise-v2025.12.12-linux-x64-musl.tar.zst"
            checksum_linux_arm64_zstd="b47a1d91156e44b46f6112bcab93121880a9ad92272349a7df74b8b4686f4ee8  ./mise-v2025.12.12-linux-arm64.tar.zst"
            checksum_linux_arm64_musl_zstd="80baba31dc0a6d96555d89e987c0edccd96a2ae922a7b191052215d89b9a8197  ./mise-v2025.12.12-linux-arm64-musl.tar.zst"
            checksum_linux_armv7_zstd="67c521a9e17e8c20679c066fa58ce8a8bf4680bbc66a5809994a2392353821a4  ./mise-v2025.12.12-linux-armv7.tar.zst"
            checksum_linux_armv7_musl_zstd="28ab5152803c078e90271bc6a4ea50b2cca1c6469fec938911eb4dfde4f09495  ./mise-v2025.12.12-linux-armv7-musl.tar.zst"
            checksum_macos_x86_64_zstd="de7a47a56415a95ed23d08d5c3ac0836553ed3df94e59e0cee82fc0abb33700b  ./mise-v2025.12.12-macos-x64.tar.zst"
            checksum_macos_arm64_zstd="8e596b9da85c1b8ddf974c81028bb4811af097094ee8f1b63118230b0018b871  ./mise-v2025.12.12-macos-arm64.tar.zst"

            # TODO: refactor this, it's a bit messy
            if [ "$ext" = "tar.zst" ]; then
              if [ "$os" = "linux" ]; then
                if [ "$arch" = "x64" ]; then
                  echo "$checksum_linux_x86_64_zstd"
                elif [ "$arch" = "x64-musl" ]; then
                  echo "$checksum_linux_x86_64_musl_zstd"
                elif [ "$arch" = "arm64" ]; then
                  echo "$checksum_linux_arm64_zstd"
                elif [ "$arch" = "arm64-musl" ]; then
                  echo "$checksum_linux_arm64_musl_zstd"
                elif [ "$arch" = "armv7" ]; then
                  echo "$checksum_linux_armv7_zstd"
                elif [ "$arch" = "armv7-musl" ]; then
                  echo "$checksum_linux_armv7_musl_zstd"
                else
                  warn "no checksum for $os-$arch"
                fi
              elif [ "$os" = "macos" ]; then
                if [ "$arch" = "x64" ]; then
                  echo "$checksum_macos_x86_64_zstd"
                elif [ "$arch" = "arm64" ]; then
                  echo "$checksum_macos_arm64_zstd"
                else
                  warn "no checksum for $os-$arch"
                fi
              else
                warn "no checksum for $os-$arch"
              fi
            else
              if [ "$os" = "linux" ]; then
                if [ "$arch" = "x64" ]; then
                  echo "$checksum_linux_x86_64"
                elif [ "$arch" = "x64-musl" ]; then
                  echo "$checksum_linux_x86_64_musl"
                elif [ "$arch" = "arm64" ]; then
                  echo "$checksum_linux_arm64"
                elif [ "$arch" = "arm64-musl" ]; then
                  echo "$checksum_linux_arm64_musl"
                elif [ "$arch" = "armv7" ]; then
                  echo "$checksum_linux_armv7"
                elif [ "$arch" = "armv7-musl" ]; then
                  echo "$checksum_linux_armv7_musl"
                else
                  warn "no checksum for $os-$arch"
                fi
              elif [ "$os" = "macos" ]; then
                if [ "$arch" = "x64" ]; then
                  echo "$checksum_macos_x86_64"
                elif [ "$arch" = "arm64" ]; then
                  echo "$checksum_macos_arm64"
                else
                  warn "no checksum for $os-$arch"
                fi
              else
                warn "no checksum for $os-$arch"
              fi
            fi
          else
            if command -v curl >/dev/null 2>&1; then
              debug ">" curl -fsSL "$url"
              checksums="$(curl --compressed -fsSL "$url")"
            else
              if command -v wget >/dev/null 2>&1; then
                debug ">" wget -qO - "$url"
                checksums="$(wget -qO - "$url")"
              else
                error "mise standalone install specific version requires curl or wget but neither is installed. Aborting."
              fi
            fi
            # TODO: verify with minisign or gpg if available

            checksum="$(echo "$checksums" | grep "$os-$arch.$ext")"
            if ! echo "$checksum" | grep -Eq "^([0-9a-f]{32}|[0-9a-f]{64})"; then
              warn "no checksum for mise $version and $os-$arch"
            else
              echo "$checksum"
            fi
          fi
        }

        #endregion

        download_file() {
          url="$1"
          download_dir="$2"
          filename="$(basename "$url")"
          file="$download_dir/$filename"

          info "mise: installing mise..."

          if command -v curl >/dev/null 2>&1; then
            debug ">" curl -#fLo "$file" "$url"
            curl -#fLo "$file" "$url"
          else
            if command -v wget >/dev/null 2>&1; then
              debug ">" wget -qO "$file" "$url"
              stderr=$(mktemp)
              wget -O "$file" "$url" >"$stderr" 2>&1 || error "wget failed: $(cat "$stderr")"
              rm "$stderr"
            else
              error "mise standalone install requires curl or wget but neither is installed. Aborting."
            fi
          fi

          echo "$file"
        }

        install_mise() {
          version="${MISE_VERSION:-v2025.12.12}"
          version="${version#v}"
          os="${MISE_INSTALL_OS:-$(get_os)}"
          arch="${MISE_INSTALL_ARCH:-$(get_arch)}"
          ext="${MISE_INSTALL_EXT:-$(get_ext)}"
          install_path="${MISE_INSTALL_PATH:-$HOME/.local/bin/mise}"
          install_dir="$(dirname "$install_path")"
          install_from_github="${MISE_INSTALL_FROM_GITHUB:-}"
          if [ "$version" != "v2025.12.12" ] || [ "$install_from_github" = "1" ] || [ "$install_from_github" = "true" ]; then
            tarball_url="https://github.com/jdx/mise/releases/download/v${version}/mise-v${version}-${os}-${arch}.${ext}"
          elif [ -n "${MISE_TARBALL_URL-}" ]; then
            tarball_url="$MISE_TARBALL_URL"
          else
            tarball_url="https://mise.jdx.dev/v${version}/mise-v${version}-${os}-${arch}.${ext}"
          fi

          download_dir="$(mktemp -d)"
          cache_file=$(download_file "$tarball_url" "$download_dir")
          debug "mise-setup: tarball=$cache_file"

          debug "validating checksum"
          cd "$(dirname "$cache_file")" && get_checksum "$version" "$os" "$arch" "$ext" | "$(shasum_bin)" -c >/dev/null

          # extract tarball
          mkdir -p "$install_dir"
          rm -rf "$install_path"
          extract_dir="$(mktemp -d)"
          cd "$extract_dir"
          if [ "$ext" = "tar.zst" ] && ! tar_supports_zstd; then
            zstd -d -c "$cache_file" | tar -xf -
          else
            tar -xf "$cache_file"
          fi
          mv mise/bin/mise "$install_path"

          # cleanup
          cd / # Move out of $extract_dir before removing it
          rm -rf "$download_dir"
          rm -rf "$extract_dir"

          info "mise: installed successfully to $install_path"
        }

        after_finish_help() {
          case "${SHELL:-}" in
          */zsh)
            info "mise: run the following to activate mise in your shell:"
            info "echo \"eval \\\"\\\$($install_path activate zsh)\\\"\" >> \"${ZDOTDIR-$HOME}/.zshrc\""
            info ""
            info "mise: run \`mise doctor\` to verify this is setup correctly"
            ;;
          */bash)
            info "mise: run the following to activate mise in your shell:"
            info "echo \"eval \\\"\\\$($install_path activate bash)\\\"\" >> ~/.bashrc"
            info ""
            info "mise: run \`mise doctor\` to verify this is setup correctly"
            ;;
          */fish)
            info "mise: run the following to activate mise in your shell:"
            info "echo \"$install_path activate fish | source\" >> ~/.config/fish/config.fish"
            info ""
            info "mise: run \`mise doctor\` to verify this is setup correctly"
            ;;
          *)
            info "mise: run \`$install_path --help\` to get started"
            ;;
          esac
        }

        install_mise
        if [ "${MISE_INSTALL_HELP-}" != 0 ]; then
          after_finish_help
        fi

        cd -- "$initial_working_dir"
    }
    local MISE_INSTALL_HELP=0
    test -f "$MISE_INSTALL_PATH" || install
}
__mise_bootstrap
exec "$MISE_INSTALL_PATH" "$@"
