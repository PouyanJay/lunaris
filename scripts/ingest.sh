#!/usr/bin/env bash
# make ingest — bulk-ingest a folder of documents into a course's grounding corpus (P6.1).
# Usage:  make ingest DIR=<folder> COURSE=<course_id>
set -euo pipefail

DIR="${DIR:-}"
COURSE="${COURSE:-}"

if [[ -z "${DIR}" || -z "${COURSE}" ]]; then
  echo "usage: make ingest DIR=<folder> COURSE=<course_id>" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec uv run python "${ROOT}/scripts/ingest.py" "${DIR}" --course "${COURSE}"
