#!/usr/bin/env bash
# Copy a job's outputs and log back from its instance (outputs/aws/JOB-instance.txt), then stop it.
# A stopped instance (the job script shuts it down, or the run outlived the laptop's watcher) is
# started first, retrying every 10 minutes for up to 12 hours when spot capacity is short; its disk
# survives a stop, so the outputs are still there. Writes the new IP back to the instance file.
#
# Usage: scripts/aws/pull.sh JOB REMOTE_PATH
# REMOTE_PATH is relative to the repo, e.g. outputs/v1/gate-qwen32b; it lands at the same place.
set -uo pipefail
JOB=$1; PULL=$2
export AWS_PROFILE=connectly
REPO=$(cd "$(dirname "$0")/../.." && pwd)
read -r R ID _ < "$REPO/outputs/aws/$JOB-instance.txt"
state() { aws ec2 describe-instances --region $R --instance-ids $ID --query 'Reservations[0].Instances[0].State.Name' --output text; }

for attempt in $(seq 1 72); do
  S=$(state)
  [ "$S" = running ] && break
  [ "$S" = stopped ] && aws ec2 start-instances --region $R --instance-ids $ID >/dev/null 2>&1 && {
    aws ec2 wait instance-running --region $R --instance-ids $ID; break; }
  echo "$(date -u +%H:%M) attempt $attempt: $S, no capacity to start; retrying in 10 minutes"
  sleep 600
done
[ "$(state)" = running ] || { echo "GAVE UP: instance still not running"; exit 1; }

IP=$(aws ec2 describe-instances --region $R --instance-ids $ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "$R $ID $IP" > "$REPO/outputs/aws/$JOB-instance.txt"
SSH="ssh -i $HOME/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 -o BatchMode=yes"
for i in $(seq 1 40); do $SSH ubuntu@$IP true 2>/dev/null && break; sleep 10; done
mkdir -p "$REPO/$(dirname "$PULL")"
rsync -az -e "$SSH" ubuntu@$IP:~/AnthropicFellow/$(basename "$REPO")/$PULL/ "$REPO/$PULL/" &&
  rsync -az -e "$SSH" ubuntu@$IP:~/logs/$JOB.log "$REPO/outputs/aws/" &&
  echo "PULLED $PULL" || { echo "PULL FAILED; instance left running: $ID"; exit 1; }
# Still running a job (pulled mid-run): leave it; otherwise stop it.
if $SSH ubuntu@$IP "tmux has-session -t $JOB" 2>/dev/null; then
  echo "job $JOB still running; instance left up"
else
  aws ec2 stop-instances --region $R --instance-ids $ID >/dev/null && echo "STOPPED $ID"
fi
