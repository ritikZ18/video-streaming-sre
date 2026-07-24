#!/usr/bin/env sh
set -eu

gitleaks detect --source . --report-path gitleaks-report.json

