#!/usr/bin/env bash
# Poll a job started by scripts/aws/launch.sh every 5 minutes. Exits when the job's tmux session
# ends, on a Python traceback (a line starting with "Traceback" or "SomethingError: "), or when the machine is not
# running. An unreachable AWS or machine (network drop on this end) means wait, not exit.
# Usage: scripts/aws/watch.sh JOB
JOB=$1
REPO=$(cd "$(dirname "$0")/../.." && pwd)
read -r R ID IP < "$REPO/outputs/aws/$JOB-instance.txt"
SSH=(ssh -i $HOME/.ssh/id_ed25519 -o ConnectTimeout=10 -o BatchMode=yes ubuntu@$IP)
while true; do
  STATE=$(AWS_PROFILE=connectly aws ec2 describe-instances --region $R --instance-ids $ID --query 'Reservations[0].Instances[0].State.Name' --output text 2>/dev/null)
  [ -z "$STATE" ] && { sleep 300; continue; }
  [ "$STATE" != running ] && { echo "MACHINE $STATE"; exit 0; }
  OUT=$("${SSH[@]}" "tmux has-session -t $JOB 2>/dev/null && echo RUNNING || echo ENDED; grep -cE '^Traceback|^[A-Za-z]*Error: ' ~/logs/$JOB.log; grep -E '^===|^---' ~/logs/$JOB.log | tail -4; true" 2>/dev/null) || { sleep 300; continue; }
  STATUS=$(echo "$OUT" | sed -n 1p); TB=$(echo "$OUT" | sed -n 2p)
  if [ "$STATUS" = ENDED ] || [ "$TB" != 0 ]; then
    echo "$OUT"; "${SSH[@]}" "grep -B2 -A12 -E '^Traceback|^[A-Za-z]*Error: ' ~/logs/$JOB.log | tail -30"
    exit 0
  fi
  sleep 300
done
