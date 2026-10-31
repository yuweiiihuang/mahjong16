#!/bin/sh
set -eu
if [ "$#" -lt 3 ] || [ "$1" != python ] || [ "$2" != -m ] || [ "$3" != app.web ]; then
    exec "$@"
fi
# Native stderr files need writable storage; keep generated lookup tables immutable in the image.
runtime=$(mktemp -d /tmp/meowcats.XXXXXX)
cp -R /opt/meowcats/runtime/. "$runtime/"
exec "$@" --meowcats-bridge /opt/meowcats/bridge --meowcats-runtime "$runtime"
