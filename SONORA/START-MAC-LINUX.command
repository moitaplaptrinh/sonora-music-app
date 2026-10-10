#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 server.py --open
fi
printf '%s\n' 'Can Python 3.10 hoac moi hon. Tai tai https://www.python.org/downloads/ .'
exit 1
