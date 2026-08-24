#!/bin/bash
# ============================================================================
# Step 1: Initial Server Setup (Run as root on fresh Ubuntu 22.04/24.04)
# Usage: ssh root@YOUR_SERVER_IP < 1-server-setup.sh
# ============================================================================
set -e

echo "========================================="
echo "  Max Pay Ads — Server Setup"
echo "========================================="

# ── Update system ────────────────────────────────────────────────────────────
apt-get update && apt-get upgrade -y

# ── Install essentials ───────────────────────────────────────────────────────
apt-get install -y \
  curl wget git ufw fail2ban htop nano \
  ca-certificates gnupg lsb-release \
  software-properties-common

# ── Create deploy user ───────────────────────────────────────────────────────
if ! id "deploy" &>/dev/null; then
  adduser --disabled-password --gecos "" deploy
  usermod -aG sudo deploy
  echo "deploy ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers.d/deploy
  # Copy SSH keys from root to deploy user
  mkdir -p /home/deploy/.ssh
  cp /root/.ssh/authorized_keys /home/deploy/.ssh/
  chown -R deploy:deploy /home/deploy/.ssh
  chmod 700 /home/deploy/.ssh
  chmod 600 /home/deploy/.ssh/authorized_keys
  echo "Created 'deploy' user with sudo access"
fi

# ── Firewall ─────────────────────────────────────────────────────────────────
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP
ufw allow 443/tcp   # HTTPS
ufw --force enable
echo "Firewall configured"

# ── Fail2Ban (brute force protection) ───────────────────────────────────────
systemctl enable fail2ban
systemctl start fail2ban

# ── Install Docker + Compose v2 plugin ───────────────────────────────────────
# get.docker.com installs Docker Engine and the `docker compose` (v2) plugin.
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
  usermod -aG docker deploy
  systemctl enable docker
  systemctl start docker
  echo "Docker installed"
fi

# Ensure the Compose v2 plugin is available (needed for deploy.resources limits).
if ! docker compose version &>/dev/null; then
  apt-get install -y docker-compose-plugin
fi
echo "Docker Compose: $(docker compose version)"

# ── Set timezone ─────────────────────────────────────────────────────────────
timedatectl set-timezone UTC

# ── Optimize system for your workload ────────────────────────────────────────
cat >> /etc/sysctl.conf <<'SYSCTL'

# Max Pay Ads optimizations
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1
vm.overcommit_memory = 1
vm.swappiness = 10
fs.file-max = 65535
SYSCTL
sysctl -p

# ── Create app directory ────────────────────────────────────────────────────
mkdir -p /home/deploy/maxpayads
chown deploy:deploy /home/deploy/maxpayads

echo ""
echo "========================================="
echo "  Server setup complete!"
echo "  Next: Log in as 'deploy' user"
echo "  ssh deploy@YOUR_SERVER_IP"
echo "========================================="
