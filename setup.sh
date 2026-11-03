#!/bin/bash
# One-time setup for the Tractus-X digital twin demo. Safe to run again.
set -e
cd "$(dirname "$0")"

SAMPLES_COMMIT=71a16a79ed3a60f3f4fd2c4cbed7d0386ef136cd   # last version with the transfer samples

step() { echo; echo "=== $1 ==="; }

step "1/5 Checking tools"
command -v git >/dev/null     || { echo "git is missing. Run: brew install git"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is missing. Run: brew install python"; exit 1; }
command -v docker >/dev/null  || { echo "Docker is missing. Install Docker Desktop."; exit 1; }
docker info >/dev/null 2>&1   || { echo "Docker is not running. Open Docker Desktop and wait for 'Engine running'."; exit 1; }
echo "OK"

step "2/5 Downloading the connector code (EDC Samples)"
if [ ! -d Samples ]; then
  git clone https://github.com/eclipse-edc/Samples.git
fi
git -C Samples fetch --quiet origin || true
git -C Samples checkout --quiet "$SAMPLES_COMMIT"
echo "OK (pinned to $SAMPLES_COMMIT)"

if docker image inspect edc-demo >/dev/null 2>&1 && [ "$1" != "--rebuild" ]; then
  step "3/5 Connectors already built on this Mac – skipping (to rebuild: bash setup.sh --rebuild)"
else
  step "3/5 Building Bob and Alice's connectors (10-20 minutes the first time)"
  docker build -t edc-demo -f Dockerfile Samples
fi

step "4/5 Downloading the Tractus-X Digital Twin Registry, its database and the part data server"
docker compose pull postgres dtr partdata

step "5/5 Setting up Python"
python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet requests

echo
echo "✅ Setup finished."
echo "   Start the demo:  bash run-demo.sh"
