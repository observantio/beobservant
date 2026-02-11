#!/bin/sh
set -e
exec gosu appuser "$@"
