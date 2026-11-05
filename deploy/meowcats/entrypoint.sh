#!/bin/sh
set -eu
# With no arguments, `exec "$@"` is a no-op and the script would run its last line instead.
if [ "$#" -eq 0 ]; then
    echo "entrypoint: no command given (image CMD is empty)" >&2
    exit 64
fi
if [ "$#" -lt 3 ] || [ "$1" != python ] || [ "$2" != -m ] || [ "$3" != app.web ]; then
    exec "$@"
fi
# Native stderr files need writable storage; keep generated lookup tables immutable in the image.
runtime=$(mktemp -d /tmp/meowcats.XXXXXX)
cp -R /opt/meowcats/runtime/. "$runtime/"
exec "$@" --meowcats-bridge /opt/meowcats/bridge --meowcats-runtime "$runtime"
