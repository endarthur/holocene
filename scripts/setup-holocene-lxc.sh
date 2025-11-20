#!/usr/bin/env bash

# Holocene LXC Setup Script for Proxmox
# Based on tteck's Proxmox script style
# Run this on your Proxmox host (rei)

set -e

# Colors
YW="\033[33m"
BL="\033[36m"
RD="\033[01;31m"
BGN="\033[4;92m"
GN="\033[1;92m"
DGN="\033[32m"
CL="\033[m"
RETRY_NUM=5
RETRY_EVERY=3
CM="${GN}✓${CL}"
CROSS="${RD}✗${CL}"
BFR="\\r\\033[K"
HOLD="-"

msg_info() {
    echo -ne " ${HOLD} ${YW}$1..."
}

msg_ok() {
    echo -e "${BFR} ${CM} ${GN}$1${CL}"
}

msg_error() {
    echo -e "${BFR} ${CROSS} ${RD}$1${CL}"
}

# Header
clear
cat <<"EOF"
    __  __      __
   / / / /___  / /___  ________  ____  ___
  / /_/ / __ \/ / __ \/ ___/ _ \/ __ \/ _ \
 / __  / /_/ / / /_/ / /__/  __/ / / /  __/
/_/ /_/\____/_/\____/\___/\___/_/ /_/\___/

Personal Knowledge Management System
LXC Container Setup for Proxmox
EOF
echo -e "\n${GN}This script will create a Holocene LXC container${CL}\n"

# Check if running on Proxmox
if ! command -v pveversion &> /dev/null; then
    msg_error "This script must be run on a Proxmox host"
    exit 1
fi

msg_ok "Running on Proxmox $(pveversion | grep "pve-manager" | awk '{print $2}')"

# Configuration
echo -e "${BL}[INFO]${CL} Configuring container settings..."

# Container ID
while true; do
    read -p "Container ID (default: 100): " CTID
    CTID=${CTID:-100}
    if pct status $CTID &>/dev/null; then
        echo -e "${RD}Container $CTID already exists${CL}"
    else
        break
    fi
done

# Hostname
read -p "Hostname (default: holocene-rei): " HOSTNAME
HOSTNAME=${HOSTNAME:-holocene-rei}

# Disk size
read -p "Disk Size in GB (default: 20): " DISK_SIZE
DISK_SIZE=${DISK_SIZE:-20}

# RAM
read -p "RAM in MB (default: 2048): " RAM
RAM=${RAM:-2048}

# CPU cores
read -p "CPU Cores (default: 2): " CORES
CORES=${CORES:-2}

# Network bridge
read -p "Network Bridge (default: vmbr0): " BRIDGE
BRIDGE=${BRIDGE:-vmbr0}

# Static IP or DHCP
read -p "Use static IP? (y/N): " USE_STATIC
if [[ "$USE_STATIC" =~ ^[Yy]$ ]]; then
    read -p "IP Address (e.g., 192.168.1.50/24): " IP_ADDRESS
    read -p "Gateway (e.g., 192.168.1.1): " GATEWAY
    NET_CONFIG="ip=$IP_ADDRESS,gw=$GATEWAY"
else
    NET_CONFIG="ip=dhcp"
fi

# Template
echo -e "\n${BL}[INFO]${CL} Available templates:"
echo "  1) Ubuntu 22.04 (recommended)"
echo "  2) Ubuntu 24.04"
echo "  3) Debian 12"
read -p "Choose template (default: 1): " TEMPLATE_CHOICE
TEMPLATE_CHOICE=${TEMPLATE_CHOICE:-1}

case $TEMPLATE_CHOICE in
    1)
        TEMPLATE="ubuntu-22.04-standard"
        OSTEMPLATE="local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"
        ;;
    2)
        TEMPLATE="ubuntu-24.04-standard"
        OSTEMPLATE="local:vztmpl/ubuntu-24.04-standard_24.04-1_amd64.tar.zst"
        ;;
    3)
        TEMPLATE="debian-12-standard"
        OSTEMPLATE="local:vztmpl/debian-12-standard_12.2-1_amd64.tar.zst"
        ;;
    *)
        msg_error "Invalid choice"
        exit 1
        ;;
esac

# Storage
# Template storage (needs to support vztmpl content type)
TEMPLATE_STORAGE=$(pvesm status -content vztmpl | awk 'NR>1 {print $1}' | head -n 1)
if [ -z "$TEMPLATE_STORAGE" ]; then
    msg_error "No storage with 'vztmpl' content type found"
    echo -e "${YW}Available storage:${CL}"
    pvesm status
    echo -e "\n${YW}Enable 'Container Templates' on a storage in Proxmox UI:${CL}"
    echo "  Datacenter → Storage → [select storage] → Edit → Content → ✓ Container Templates"
    exit 1
fi

# Container storage (needs to support rootdir content type)
CONTAINER_STORAGE=$(pvesm status -content rootdir | awk 'NR>1 {print $1}' | head -n 1)
if [ -z "$CONTAINER_STORAGE" ]; then
    msg_error "No storage with 'rootdir' content type found"
    exit 1
fi

# Summary
echo -e "\n${BL}[INFO]${CL} Configuration Summary:"
echo "  CTID:     $CTID"
echo "  Hostname: $HOSTNAME"
echo "  Template: $TEMPLATE"
echo "  Disk:     ${DISK_SIZE}GB"
echo "  RAM:      ${RAM}MB"
echo "  Cores:    $CORES"
echo "  Network:  $BRIDGE ($NET_CONFIG)"
echo "  Template Storage: $TEMPLATE_STORAGE"
echo "  Container Storage: $CONTAINER_STORAGE"
echo ""

read -p "Proceed with creation? (Y/n): " CONFIRM
if [[ "$CONFIRM" =~ ^[Nn]$ ]]; then
    msg_error "Aborted by user"
    exit 1
fi

# Update template list
msg_info "Updating template list"
pveam update &>/dev/null
msg_ok "Template list updated"

# Check if template exists
msg_info "Checking for template"
if ! pveam list "$TEMPLATE_STORAGE" | grep -q "$TEMPLATE"; then
    msg_info "Downloading template: $TEMPLATE"
    pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
    msg_ok "Template downloaded"
else
    msg_ok "Template found"
fi

# Create container
msg_info "Creating LXC container"
pct create "$CTID" "$OSTEMPLATE" \
    --hostname "$HOSTNAME" \
    --cores "$CORES" \
    --memory "$RAM" \
    --rootfs "$CONTAINER_STORAGE:$DISK_SIZE" \
    --net0 "name=eth0,bridge=$BRIDGE,$NET_CONFIG" \
    --features nesting=1 \
    --unprivileged 1 \
    --onboot 1 \
    --start 0
msg_ok "Container created"

# Set password
msg_info "Setting root password"
echo "root:holocene" | pct exec "$CTID" -- chpasswd
msg_ok "Root password set to: holocene"

# Start container
msg_info "Starting container"
pct start "$CTID"
sleep 5
msg_ok "Container started"

# Wait for network
msg_info "Waiting for network"
for _ in {1..30}; do
    if pct exec "$CTID" -- ping -c 1 8.8.8.8 &>/dev/null; then
        break
    fi
    sleep 1
done
msg_ok "Network ready"

# Get container IP
CONTAINER_IP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
msg_ok "Container IP: $CONTAINER_IP"

# Download and run bootstrap script
msg_info "Running bootstrap script"
pct exec "$CTID" -- bash -c "wget -qO- https://raw.githubusercontent.com/endarthur/holocene/main/scripts/bootstrap-holocene.sh | bash"
msg_ok "Bootstrap complete"

# Summary
echo -e "\n${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
echo -e "${GN}✓ Holocene LXC Container Created Successfully!${CL}"
echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
echo -e "\n${BL}Container Details:${CL}"
echo "  ID:       $CTID"
echo "  Hostname: $HOSTNAME"
echo "  IP:       $CONTAINER_IP"
echo "  mDNS:     http://${HOSTNAME}.local:5555"
echo ""
echo -e "${BL}Login:${CL}"
echo "  User:     root"
echo "  Password: holocene"
echo ""
echo -e "${BL}Access Container:${CL}"
echo "  pct enter $CTID"
echo ""
echo -e "${BL}Holocene API:${CL}"
echo "  http://$CONTAINER_IP:5555"
echo "  http://${HOSTNAME}.local:5555"
echo ""
echo -e "${BL}Check Status:${CL}"
echo "  pct exec $CTID -- systemctl status holod"
echo ""
echo -e "${BL}View Logs:${CL}"
echo "  pct exec $CTID -- journalctl -u holod -f"
echo ""
echo -e "${YW}⚠ Don't forget to:${CL}"
echo "  1. Change root password: pct enter $CTID && passwd"
echo "  2. Configure API keys: edit ~/.config/holocene/config.yml"
echo "  3. Set up Cloudflare Tunnel (if needed)"
echo "  4. Install Tailscale (if needed)"
echo ""
