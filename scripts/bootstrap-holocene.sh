#!/usr/bin/env bash

# Holocene Bootstrap Script
# Runs inside the LXC container to install and configure Holocene
# This script is called by setup-holocene-lxc.sh

set -e

# Colors
YW="\033[33m"
BL="\033[36m"
RD="\033[01;31m"
GN="\033[1;92m"
CL="\033[m"

msg_info() {
    echo -e " ${YW}➜${CL} $1..."
}

msg_ok() {
    echo -e " ${GN}✓${CL} $1"
}

msg_error() {
    echo -e " ${RD}✗${CL} $1"
    exit 1
}

echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
echo -e "${GN}Holocene Bootstrap Script${CL}"
echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"

# Update system
msg_info "Updating system packages"
apt-get update -qq &>/dev/null
apt-get upgrade -y -qq &>/dev/null
msg_ok "System updated"

# Install dependencies
msg_info "Installing dependencies"
apt-get install -y -qq \
    python3.11 \
    python3.11-venv \
    python3-pip \
    git \
    curl \
    avahi-daemon \
    avahi-utils \
    libnss-mdns \
    build-essential \
    &>/dev/null
msg_ok "Dependencies installed"

# Enable and start Avahi (mDNS)
msg_info "Configuring mDNS (Avahi)"
systemctl enable avahi-daemon &>/dev/null
systemctl start avahi-daemon &>/dev/null
msg_ok "mDNS configured"

# Create holocene user
msg_info "Creating holocene user"
if ! id -u holocene &>/dev/null; then
    useradd -m -s /bin/bash -G sudo holocene
    echo "holocene:holocene" | chpasswd
    msg_ok "User created (password: holocene)"
else
    msg_ok "User already exists"
fi

# Clone repository
msg_info "Cloning Holocene repository"
if [ ! -d "/home/holocene/holocene" ]; then
    su - holocene -c "git clone https://github.com/endarthur/holocene.git /home/holocene/holocene" &>/dev/null
    msg_ok "Repository cloned"
else
    msg_ok "Repository already exists"
fi

# Create virtual environment
msg_info "Creating Python virtual environment"
su - holocene -c "cd /home/holocene/holocene && python3.11 -m venv venv" &>/dev/null
msg_ok "Virtual environment created"

# Install Holocene with all optional dependencies
msg_info "Installing Holocene"
su - holocene -c "cd /home/holocene/holocene && source venv/bin/activate && pip install -q --upgrade pip && pip install -q -e '.[all]'" &>/dev/null
msg_ok "Holocene installed"

# Initialize Holocene
msg_info "Initializing Holocene"
su - holocene -c "cd /home/holocene/holocene && source venv/bin/activate && holo init" &>/dev/null || true
msg_ok "Holocene initialized"

# Ensure directories exist for systemd mount namespacing
msg_info "Creating holocene directories"
mkdir -p /home/holocene/.holocene
mkdir -p /home/holocene/.config/holocene
chown -R holocene:holocene /home/holocene/.holocene
chown -R holocene:holocene /home/holocene/.config/holocene
msg_ok "Directories created"

# Create systemd service
msg_info "Creating systemd service"
cat > /etc/systemd/system/holod.service <<'EOF'
[Unit]
Description=Holocene Daemon
Documentation=https://github.com/endarthur/holocene
After=network-online.target avahi-daemon.service
Wants=network-online.target

[Service]
Type=simple
User=holocene
Group=holocene
WorkingDirectory=/home/holocene/holocene
Environment="PATH=/home/holocene/holocene/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/home/holocene/holocene/venv/bin/holo daemon start --foreground --device rei
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=holod

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/holocene/.holocene /home/holocene/.config/holocene

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable holod &>/dev/null
msg_ok "Systemd service created"

# Create MOTD
msg_info "Creating custom MOTD"
rm -f /etc/update-motd.d/*
cat > /etc/update-motd.d/00-holocene <<'EOF'
#!/bin/bash
HOSTNAME=$(hostname)
IP=$(hostname -I | awk '{print $1}')
TAILSCALE_IP=$(tailscale ip 2>/dev/null | head -n1)
HOLOD_STATUS=$(systemctl is-active holod 2>/dev/null || echo "inactive")

# Color codes
GREEN='\033[1;92m'
BLUE='\033[1;36m'
YELLOW='\033[1;33m'
RED='\033[1;31m'
RESET='\033[0m'

if [ "$HOLOD_STATUS" = "active" ]; then
    STATUS="${GREEN}● Running${RESET}"
else
    STATUS="${RED}● Stopped${RESET}"
fi

echo -e "${BLUE}"
cat << 'LOGO'
    __  __      __
   / / / /___  / /___  ________  ____  ___
  / /_/ / __ \/ / __ \/ ___/ _ \/ __ \/ _ \
 / __  / /_/ / / /_/ / /__/  __/ / / /  __/
/_/ /_/\____/_/\____/\___/\___/_/ /_/\___/
LOGO
echo -e "${RESET}"
echo -e "${GREEN}Personal Knowledge Management System${RESET}"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════${RESET}"
echo -e "${BLUE}Network:${RESET}"
echo -e "  IPv4:     ${YELLOW}$IP${RESET}"
if [ -n "$TAILSCALE_IP" ]; then
echo -e "  Tailscale: ${YELLOW}$TAILSCALE_IP${RESET}"
fi
echo -e "  mDNS:     ${YELLOW}$HOSTNAME.local${RESET}"
echo ""
echo -e "${BLUE}API Endpoint:${RESET}"
echo -e "  ${YELLOW}http://$HOSTNAME.local:5555${RESET}"
echo -e "  ${YELLOW}http://$IP:5555${RESET}"
echo ""
echo -e "${BLUE}Holod Status:${RESET} $STATUS"
echo -e "${BLUE}═══════════════════════════════════════════════${RESET}"
echo ""
echo -e "${BLUE}Useful Commands:${RESET}"
echo -e "  systemctl status holod      # Check daemon status"
echo -e "  journalctl -u holod -f      # View live logs"
echo -e "  holo daemon status          # Holocene CLI status"
echo -e "  holo daemon restart         # Restart daemon"
echo ""
echo -e "${BLUE}Configuration:${RESET}"
echo -e "  ~/.config/holocene/config.yml"
echo -e "  ~/.holocene/holocene.db"
echo ""
EOF

chmod +x /etc/update-motd.d/00-holocene
msg_ok "Custom MOTD created"

# Create convenient aliases
msg_info "Creating shell aliases"
cat >> /home/holocene/.bashrc <<'EOF'

# Holocene aliases
alias holod-status='systemctl status holod'
alias holod-logs='journalctl -u holod -f'
alias holod-restart='sudo systemctl restart holod'
alias holo-config='nano ~/.config/holocene/config.yml'
alias holo-db='sqlite3 ~/.holocene/holocene.db'

# Activate venv by default
cd /home/holocene/holocene
source venv/bin/activate
EOF

chown holocene:holocene /home/holocene/.bashrc
msg_ok "Shell aliases created"

# Create update script
msg_info "Creating update script"
cat > /usr/local/bin/update-holocene <<'EOF'
#!/bin/bash
echo "Updating Holocene..."
cd /home/holocene/holocene
git pull
source venv/bin/activate
pip install -e . --upgrade
sudo systemctl restart holod
echo "✓ Holocene updated!"
EOF

chmod +x /usr/local/bin/update-holocene
msg_ok "Update script created"

# Start holod
msg_info "Starting Holocene daemon"
systemctl start holod
sleep 3

if systemctl is-active --quiet holod; then
    msg_ok "Holod started successfully"
else
    msg_error "Failed to start holod"
fi

# Final summary
CONTAINER_IP=$(hostname -I | awk '{print $1}')
CONTAINER_HOSTNAME=$(hostname)

echo ""
echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
echo -e "${GN}✓ Holocene Bootstrap Complete!${CL}"
echo -e "${GN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${CL}"
echo ""
echo -e "${BL}API Access:${CL}"
echo -e "  http://$CONTAINER_IP:5555"
echo -e "  http://${CONTAINER_HOSTNAME}.local:5555"
echo ""
echo -e "${BL}Daemon Status:${CL}"
echo -e "  systemctl status holod"
echo ""
echo -e "${YW}⚠ Next Steps:${CL}"
echo -e "  1. Edit config: nano ~/.config/holocene/config.yml"
echo -e "  2. Add NanoGPT API key"
echo -e "  3. Configure Telegram bot (optional)"
echo -e "  4. Test API: curl http://$CONTAINER_IP:5555/status"
echo ""
