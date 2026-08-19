#!/usr/bin/env bash
# Build the backend image locally, ship it over SSH, start the stack.
# Usage: deploy/deploy.sh <vm-ip> [ssh-user]
set -euo pipefail

VM_IP=${1:?usage: deploy.sh <vm-ip> [ssh-user]}
SSH_USER=${2:-gnl}
HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(dirname "$HERE")

test -f "$HERE/.env" || { echo "deploy/.env is missing; copy deploy/env.example"; exit 1; }

echo "== build =="
docker build -t gnl-backend:staging "$REPO"

echo "== ship the image =="
docker save gnl-backend:staging | gzip | ssh "$SSH_USER@$VM_IP" 'gunzip | docker load'

echo "== ship the stack files =="
scp "$HERE/compose.yaml" "$HERE/.env" "$SSH_USER@$VM_IP:~/"

echo "== start =="
ssh "$SSH_USER@$VM_IP" 'docker compose -f ~/compose.yaml --env-file ~/.env up -d'

echo "== smoke =="
sleep 5
ssh "$SSH_USER@$VM_IP" 'curl -sf http://localhost:5002/seasons > /dev/null' && echo "backend answers"
