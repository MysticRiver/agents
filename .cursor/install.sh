#!/usr/bin/env bash
# Idempotent setup for the VideoSDK AI Agents development environment.
# Safe to run repeatedly; it refreshes system packages, the Python virtual
# environment, editable SDK/plugin installs, Git LFS assets, and the native
# RNNoise library.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY=python3.12

# ---------------------------------------------------------------------------
# 1) System packages
#    - build toolchain (build-essential/meson/ninja/cmake/swig) + Python headers
#      are required to compile aec-audio-processing (bundled webrtc-audio-processing).
#    - autoconf/automake/libtool(-bin) build the native RNNoise library.
#    - libportaudio2 is a runtime dependency of sounddevice; ffmpeg for media.
# ---------------------------------------------------------------------------
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
fi

APT_PACKAGES=(
  build-essential
  python3.12-venv
  python3.12-dev
  meson
  ninja-build
  pkg-config
  cmake
  swig
  autoconf
  automake
  libtool
  libtool-bin
  libportaudio2
  ffmpeg
  git-lfs
)

if command -v apt-get >/dev/null 2>&1; then
  $SUDO apt-get update -qq || true
  DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends "${APT_PACKAGES[@]}"
else
  echo "WARN: apt-get not available; assuming system dependencies are present." >&2
fi

# ---------------------------------------------------------------------------
# 2) Git LFS assets (e.g. Silero VAD ONNX model shipped via LFS)
# ---------------------------------------------------------------------------
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install --local || true
  git lfs pull || echo "WARN: 'git lfs pull' failed; LFS assets may be missing." >&2
fi

# ---------------------------------------------------------------------------
# 3) Python virtual environment
# ---------------------------------------------------------------------------
if [ ! -x "venv/bin/python" ]; then
  "$PY" -m venv venv
fi
# shellcheck disable=SC1091
source venv/bin/activate

python -m pip install --upgrade pip setuptools wheel

# Force the GNU toolchain for source builds: the default `cc`/`c++` on this
# image is clang, which fails to link libstdc++ when compiling the bundled
# webrtc-audio-processing sources.
export CC="${CC:-gcc}"
export CXX="${CXX:-g++}"

# ---------------------------------------------------------------------------
# 4) Core dependencies + editable SDK/plugin installs
# ---------------------------------------------------------------------------
# Install PyAV from a wheel first. The newest av in the allowed range (14.4.0)
# ships no cp312 wheel and would otherwise fall back to a source build that
# needs system FFmpeg dev headers; --only-binary pins to the newest wheel.
pip install --only-binary=:all: "av>=14.0.0,<15.0.0"

pip install -r requirements.txt

# The `videosdk` namespace is split across the PyPI `videosdk` package and the
# local `videosdk.agents` / `videosdk.plugins.*` packages. Make it a proper
# pkgutil-style namespace so all sub-packages resolve.
VIDEOSDK_INIT="$(python -c 'import videosdk, os; print(os.path.join(os.path.dirname(videosdk.__file__), "__init__.py"))' 2>/dev/null || true)"
if [ -n "$VIDEOSDK_INIT" ] && [ -f "$VIDEOSDK_INIT" ]; then
  if ! grep -q "extend_path" "$VIDEOSDK_INIT"; then
    echo "__path__ = __import__('pkgutil').extend_path(__path__, __name__)" >> "$VIDEOSDK_INIT"
  fi
fi

pip install -e ./videosdk-agents
for plugin in videosdk-plugins/*; do
  if [ -f "$plugin/pyproject.toml" ]; then
    pip install -e "$plugin"
  fi
done

# ---------------------------------------------------------------------------
# 5) Compatibility pins + undeclared transitive deps
#    The SDK's requirements are unpinned; newer releases of these packages
#    renamed public symbols the SDK imports. Pin to the versions that match
#    the SDK release (v0.0.54, Dec 2025).
#      - mcp>=2.0 renamed streamablehttp_client -> streamable_http_client
#      - aws-sdk-bedrock-runtime>=0.3 changed BedrockRuntimeClient's location
#      - videosdk-plugins-smallestai imports aiofiles without declaring it
# ---------------------------------------------------------------------------
pip install "mcp==1.25.0" "aws_sdk_bedrock_runtime==0.2.0" "aiofiles"

# ---------------------------------------------------------------------------
# 6) Build the native RNNoise library for Linux (repo ships only the macOS one)
# ---------------------------------------------------------------------------
RNNOISE_DIR="videosdk-plugins/videosdk-plugins-rnnoise/videosdk/plugins/rnnoise"
if [ ! -f "$RNNOISE_DIR/files/librnnoise.so" ]; then
  python "$RNNOISE_DIR/build_rnnoise.py" || \
    echo "WARN: RNNoise build failed; the rnnoise plugin will be unavailable." >&2
fi

echo "VideoSDK AI Agents environment ready."
