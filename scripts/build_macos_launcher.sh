#!/bin/zsh
set -eu
cd -- "$(dirname -- "$0")/.."
clang -arch arm64 -mmacosx-version-min=11.0 -O2 scripts/macos_launcher.c -o 'Thesis Monitor.app/Contents/MacOS/ThesisMonitor'
codesign --force --sign - 'Thesis Monitor.app'
