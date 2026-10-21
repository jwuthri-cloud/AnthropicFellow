#!/usr/bin/env bash
# Launch one GPU job on Connectly's AWS (never RunPod): a p5.4xlarge (1x H100), spot first, then
# on-demand, in the US regions and Stockholm, retried every 10 minutes for up to 6 hours. Copies THIS
# repo and ../EvalGamingUnderPressureTraining side by side into ~/AnthropicFellow/ (the uv path
# dependency needs both), installs, and starts RUN_SCRIPT in tmux session JOB, logging to
# ~/logs/JOB.log. The job script shuts the machine down when it ends.
# ponytail: adapted copy of the eval-gaming launch.sh (same key pair and security group); merge the
# two into one parametrized script if a third project needs it.
#
# Usage: scripts/aws/launch.sh JOB RUN_SCRIPT VOLUME_GB
# Writes outputs/aws/JOB-instance.txt ("region instance-id ip") for scripts/aws/watch.sh.
set -uo pipefail
JOB=$1; RUN=$2; VOLUME=$3
export AWS_PROFILE=connectly
REPO=$(cd "$(dirname "$0")/../.." && pwd)
DEP=$(cd "$REPO/../EvalGamingUnderPressureTraining" && pwd)
KEY=$HOME/.ssh/id_ed25519
TAGS='{Key=Name,Value=asimov},{Key=Owner,Value=julien},{Key=Project,Value=asimov}'
REGIONS="us-east-2 us-east-1 us-west-2 eu-north-1"
MYIP=$(curl -s --max-time 10 https://checkip.amazonaws.com)
mkdir -p "$REPO/outputs/aws"

try_region() {  # region market -> prints "region instance-id" on success
  local R=$1 M=$2 VPC AMI SG SUBNET OUT MARKET=()
  VPC=$(aws ec2 describe-vpcs --region $R --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
  AMI=$(aws ec2 describe-images --region $R --owners amazon --filters "Name=name,Values=Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 24.04)*" --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)
  SG=$(aws ec2 describe-security-groups --region $R --filters Name=vpc-id,Values=$VPC Name=group-name,Values=evalgaming-pilot --query 'SecurityGroups[0].GroupId' --output text)
  aws ec2 authorize-security-group-ingress --region $R --group-id $SG --protocol tcp --port 22 --cidr "$MYIP/32" >/dev/null 2>&1  # already allowed: no-op
  [ "$M" = spot ] && MARKET=(--instance-market-options 'MarketType=spot,SpotOptions={SpotInstanceType=persistent,InstanceInterruptionBehavior=stop}')
  for SUBNET in $(aws ec2 describe-subnets --region $R --filters Name=vpc-id,Values=$VPC --query 'Subnets[].SubnetId' --output text); do
    OUT=$(aws ec2 run-instances --region $R --image-id $AMI --instance-type p5.4xlarge --count 1 \
      --key-name evalgaming-pilot-julien --security-group-ids $SG --subnet-id $SUBNET --associate-public-ip-address "${MARKET[@]}" \
      --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":$VOLUME,\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
      --instance-initiated-shutdown-behavior stop --metadata-options HttpTokens=required \
      --tag-specifications "ResourceType=instance,Tags=[$TAGS]" "ResourceType=volume,Tags=[$TAGS]" \
      --query 'Instances[0].InstanceId' --output text 2>&1)
    case "$OUT" in i-*) echo "$R $OUT"; return 0;; esac
  done
  return 1
}

FOUND=""
for attempt in $(seq 1 36); do
  for M in spot od; do
    for R in $REGIONS; do FOUND=$(try_region $R $M) && break 2; done
  done
  [ -n "$FOUND" ] && break
  echo "$(date -u +%H:%M) attempt $attempt: no H100 anywhere"
  sleep 600
done
[ -z "$FOUND" ] && { echo "GAVE UP after 6 hours, nothing launched"; exit 1; }

read -r REGION ID <<< "$FOUND"
echo "LAUNCHED $ID in $REGION at $(date -u +%H:%M)"
aws ec2 wait instance-running --region $REGION --instance-ids $ID
IP=$(aws ec2 describe-instances --region $REGION --instance-ids $ID --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
echo "$REGION $ID $IP" > "$REPO/outputs/aws/$JOB-instance.txt"
SSH=(ssh -i $KEY -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 -o BatchMode=yes -o ServerAliveInterval=60 ubuntu@$IP)
for i in $(seq 1 40); do "${SSH[@]}" true 2>/dev/null && break; sleep 10; done
EXCLUDES=(--exclude .venv --exclude .ruff_cache --exclude .pytest_cache --exclude __pycache__ --exclude outputs)
"${SSH[@]}" "mkdir -p ~/AnthropicFellow ~/logs"
for SRC in "$DEP" "$REPO"; do
  rsync -az "${EXCLUDES[@]}" -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" "$SRC/" ubuntu@$IP:~/AnthropicFellow/$(basename "$SRC")/
done
"${SSH[@]}" "curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; cd ~/AnthropicFellow/$(basename "$REPO") && ~/.local/bin/uv sync --extra gpu --python 3.12 >/dev/null 2>&1 && tmux new -d -s $JOB '$RUN > ~/logs/$JOB.log 2>&1' && sleep 5 && tmux has-session -t $JOB && echo '$JOB started'; head -5 ~/logs/$JOB.log"
