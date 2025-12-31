#!/bin/bash
# Setup script for Laney's sandbox LXC container on Proxmox
#
# Run this on the Proxmox host (not inside a container)
# Usage: bash setup_laney_sandbox.sh
#
# Prerequisites:
#   - Proxmox VE with pveam templates
#   - SSH access to Proxmox host

set -e

# Configuration
VMID=200                          # Container ID (adjust if 200 is taken)
HOSTNAME="laney-sandbox"
STORAGE="local-lvm"               # Your Proxmox storage (check with: pvesm status)
TEMPLATE="local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst"
MEMORY=2048                       # 2GB RAM
SWAP=512
CORES=2
DISK_SIZE=16                      # 16GB disk
BRIDGE="vmbr0"                    # Network bridge

echo "=== Laney Sandbox LXC Setup ==="
echo "VMID: $VMID"
echo "Hostname: $HOSTNAME"
echo ""

# Check if template exists, download if not
echo "[1/7] Checking template..."
if ! pveam list local | grep -q "debian-12-standard"; then
    echo "Downloading Debian 12 template..."
    pveam download local debian-12-standard_12.2-1_amd64.tar.zst
fi

# Create unprivileged container
echo "[2/7] Creating LXC container..."
pct create $VMID $TEMPLATE \
    --hostname $HOSTNAME \
    --memory $MEMORY \
    --swap $SWAP \
    --cores $CORES \
    --rootfs ${STORAGE}:${DISK_SIZE} \
    --net0 name=eth0,bridge=$BRIDGE,ip=dhcp \
    --unprivileged 1 \
    --features nesting=1 \
    --onboot 1 \
    --start 0

# Start container
echo "[3/7] Starting container..."
pct start $VMID
sleep 5  # Wait for network

# Get container IP
echo "[4/7] Getting container IP..."
CT_IP=$(pct exec $VMID -- hostname -I | awk '{print $1}')
echo "Container IP: $CT_IP"

# Install packages inside container
echo "[5/7] Installing packages (this takes a few minutes)..."
pct exec $VMID -- bash -c '
    apt-get update
    apt-get install -y \
        python3 python3-pip python3-venv \
        openssh-server \
        curl wget git jq \
        build-essential \
        sqlite3

    # Create Python virtual environment with scientific stack
    python3 -m venv /opt/sandbox-env
    /opt/sandbox-env/bin/pip install --upgrade pip
    /opt/sandbox-env/bin/pip install \
        numpy pandas scipy matplotlib seaborn \
        scikit-learn statsmodels \
        requests beautifulsoup4 lxml \
        pyyaml toml jsonschema \
        ipython

    # Create sandbox user
    useradd -m -s /bin/bash sandbox
    mkdir -p /home/sandbox/.ssh
    chmod 700 /home/sandbox/.ssh
    chown -R sandbox:sandbox /home/sandbox

    # Create workspace directory
    mkdir -p /workspace
    chown sandbox:sandbox /workspace

    # Add venv to sandbox user path
    echo "source /opt/sandbox-env/bin/activate" >> /home/sandbox/.bashrc
    echo "cd /workspace" >> /home/sandbox/.bashrc

    # Configure SSH
    sed -i "s/#PasswordAuthentication yes/PasswordAuthentication no/" /etc/ssh/sshd_config
    systemctl enable ssh
    systemctl restart ssh
'

# Setup SSH key from rei
echo "[6/7] Setting up SSH key access..."
echo ""
echo "Now run this on holocene-rei to setup SSH access:"
echo "=============================================="
echo ""
echo "# Generate key if needed:"
echo "ssh-keygen -t ed25519 -f ~/.ssh/laney_sandbox -N ''"
echo ""
echo "# Copy public key to sandbox:"
echo "cat ~/.ssh/laney_sandbox.pub | ssh root@<PROXMOX_HOST> 'pct exec $VMID -- bash -c \"cat >> /home/sandbox/.ssh/authorized_keys && chown sandbox:sandbox /home/sandbox/.ssh/authorized_keys && chmod 600 /home/sandbox/.ssh/authorized_keys\"'"
echo ""
echo "# Add to SSH config (~/.ssh/config):"
echo "Host laney-sandbox"
echo "    HostName $CT_IP"
echo "    User sandbox"
echo "    IdentityFile ~/.ssh/laney_sandbox"
echo "    StrictHostKeyChecking no"
echo ""
echo "# Test connection:"
echo "ssh laney-sandbox 'python3 -c \"import numpy; print(numpy.__version__)\"'"
echo ""
echo "=============================================="

# Summary
echo "[7/7] Done!"
echo ""
echo "Container created: $HOSTNAME (VMID: $VMID)"
echo "IP Address: $CT_IP"
echo "Memory: ${MEMORY}MB"
echo "Disk: ${DISK_SIZE}GB"
echo ""
echo "Installed:"
echo "  - Python 3 + scientific stack (numpy, pandas, scipy, matplotlib, sklearn)"
echo "  - CLI tools (curl, wget, git, jq, sqlite3)"
echo "  - SSH server (key-based auth only)"
echo ""
echo "Next: Configure SSH access from holocene-rei (see commands above)"
