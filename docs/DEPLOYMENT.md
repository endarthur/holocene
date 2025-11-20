# Holocene Deployment Guide

Complete guide for deploying Holocene on Proxmox LXC containers.

## Quick Start (TL;DR)

```bash
# On Proxmox host (rei)
curl -fsSL https://raw.githubusercontent.com/endarthur/holocene/main/scripts/setup-holocene-lxc.sh | bash

# That's it! The script handles everything.
```

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Methods](#deployment-methods)
3. [Automated Deployment (Recommended)](#automated-deployment)
4. [Manual Deployment](#manual-deployment)
5. [Post-Deployment Configuration](#post-deployment-configuration)
6. [Network Setup](#network-setup)
7. [Cloudflare Tunnel](#cloudflare-tunnel)
8. [Tailscale](#tailscale)
9. [Monitoring and Maintenance](#monitoring-and-maintenance)
10. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Proxmox VE 7.x or 8.x
- Available LXC container ID (default: 100)
- Network connectivity (internet access for downloads)
- At least 2GB RAM and 20GB storage available

## Deployment Methods

### Method 1: Automated (Recommended)

Single command deployment using our tteck-style script.

### Method 2: Manual

Step-by-step manual installation for customization.

---

## Automated Deployment

### Step 1: Download and Run Setup Script

On your Proxmox host (rei):

```bash
curl -fsSL https://raw.githubusercontent.com/endarthur/holocene/main/scripts/setup-holocene-lxc.sh -o setup-holocene-lxc.sh
chmod +x setup-holocene-lxc.sh
./setup-holocene-lxc.sh
```

The script will prompt you for:
- Container ID (default: 100)
- Hostname (default: holocene-rei)
- Disk size (default: 20GB)
- RAM (default: 2048MB)
- CPU cores (default: 2)
- Network bridge (default: vmbr0)
- IP configuration (DHCP or static)
- OS template (Ubuntu 22.04 recommended)

### Step 2: Access Container

```bash
# From Proxmox host
pct enter 100

# Or SSH (after setting up keys)
ssh root@holocene.local
```

### Step 3: Configure Holocene

```bash
# Edit configuration
nano ~/.config/holocene/config.yml

# Add your NanoGPT API key
llm:
  api_key: "your-nanogpt-api-key"

# Add Telegram bot token (optional)
telegram:
  bot_token: "your-telegram-bot-token"
  chat_id: your-chat-id

# Restart daemon
systemctl restart holod
```

### Step 4: Verify Installation

```bash
# Check daemon status
systemctl status holod

# View logs
journalctl -u holod -f

# Test API
curl http://localhost:5555/status
```

---

## Manual Deployment

### Step 1: Create LXC Container

```bash
# On Proxmox host
pct create 100 local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst \
  --hostname holocene-rei \
  --cores 2 \
  --memory 2048 \
  --rootfs local-lvm:20 \
  --net0 name=eth0,bridge=vmbr0,ip=dhcp \
  --features nesting=1 \
  --unprivileged 1 \
  --onboot 1

# Start container
pct start 100

# Enter container
pct enter 100
```

### Step 2: Update System

```bash
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3-pip git curl \
               avahi-daemon avahi-utils libnss-mdns build-essential
```

### Step 3: Enable mDNS

```bash
systemctl enable avahi-daemon
systemctl start avahi-daemon

# Test
ping holocene-rei.local
```

### Step 4: Create User

```bash
useradd -m -s /bin/bash -G sudo holocene
passwd holocene
```

### Step 5: Install Holocene

```bash
su - holocene
git clone https://github.com/endarthur/holocene.git
cd holocene
python3.11 -m venv venv
source venv/bin/activate
pip install -e .
holo init
```

### Step 6: Create Systemd Service

```bash
sudo nano /etc/systemd/system/holod.service
```

Paste:

```ini
[Unit]
Description=Holocene Daemon
After=network-online.target avahi-daemon.service
Wants=network-online.target

[Service]
Type=simple
User=holocene
WorkingDirectory=/home/holocene/holocene
Environment="PATH=/home/holocene/holocene/venv/bin"
ExecStart=/home/holocene/holocene/venv/bin/holo daemon start --foreground --device rei
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable holod
sudo systemctl start holod
```

---

## Post-Deployment Configuration

### API Keys

Edit `~/.config/holocene/config.yml`:

```yaml
llm:
  api_key: "sk-..." # Your NanoGPT API key
  base_url: "https://nano-gpt.com/api"
  primary: "deepseek-ai/DeepSeek-V3.1"

telegram:
  bot_token: "123456:ABC-DEF..." # Optional
  chat_id: 123456789
```

### Database Location

Default: `~/.holocene/holocene.db`

To change:

```yaml
data_dir: /custom/path
```

### Logging

View logs:

```bash
journalctl -u holod -f           # Live logs
journalctl -u holod --since today  # Today's logs
journalctl -u holod -n 100        # Last 100 lines
```

---

## Network Setup

### Local Network (mDNS)

**Automatically configured by bootstrap script.**

Access from any device on LAN:
- `http://holocene-rei.local:5555`
- `http://192.168.1.50:5555` (your IP)

Test:

```bash
# From wmut
ping holocene-rei.local
curl http://holocene-rei.local:5555/status
```

### Static IP Configuration

If you need to change IP after deployment:

```bash
# On Proxmox host
pct set 100 --net0 name=eth0,bridge=vmbr0,ip=192.168.1.50/24,gw=192.168.1.1

# Restart container
pct restart 100
```

---

## Cloudflare Tunnel

### Option A: Reuse Existing Tunnel (Recommended)

If you already have cloudflared running on rei:

1. Edit your existing tunnel config:

```bash
# On rei (or wherever cloudflared runs)
nano /etc/cloudflared/config.yml
```

2. Add Holocene route:

```yaml
tunnel: your-tunnel-id
credentials-file: /etc/cloudflared/your-tunnel-credentials.json

ingress:
  - hostname: holocene.yourdomain.com
    service: http://192.168.1.50:5555
  # ... your other routes
  - service: http_status:404
```

3. Restart cloudflared:

```bash
systemctl restart cloudflared
```

4. Add DNS record in Cloudflare dashboard:
   - Type: CNAME
   - Name: holocene
   - Content: your-tunnel-id.cfargotunnel.com

### Option B: New Tunnel in LXC

1. Enter holocene container:

```bash
pct enter 100
```

2. Install cloudflared:

```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
dpkg -i cloudflared.deb
```

3. Authenticate:

```bash
cloudflared tunnel login
```

4. Create tunnel:

```bash
cloudflared tunnel create holocene
```

5. Configure:

```bash
nano ~/.cloudflared/config.yml
```

```yaml
tunnel: holocene-tunnel-id
credentials-file: /root/.cloudflared/holocene-tunnel-id.json

ingress:
  - hostname: holocene.yourdomain.com
    service: http://localhost:5555
  - service: http_status:404
```

6. Route DNS:

```bash
cloudflared tunnel route dns holocene holocene.yourdomain.com
```

7. Run as service:

```bash
cloudflared service install
systemctl enable cloudflared
systemctl start cloudflared
```

---

## Tailscale

### Install Tailscale in Container

1. Enter container:

```bash
pct enter 100
```

2. Install Tailscale:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
```

3. Authenticate:

```bash
tailscale up
```

4. Get Tailscale IP:

```bash
tailscale ip -4
```

5. Access from anywhere:

```bash
# Via MagicDNS
curl http://holocene-rei:5555/status

# Via IP
curl http://100.x.x.x:5555/status
```

### Configure Tailscale ACLs (Optional)

In Tailscale admin console, add ACL:

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["autogroup:members"],
      "dst": ["holocene-rei:5555"]
    }
  ]
}
```

---

## Monitoring and Maintenance

### Health Checks

```bash
# Daemon status
systemctl status holod

# API health
curl http://localhost:5555/health

# Full status
curl http://localhost:5555/status | jq

# Plugin list
curl http://localhost:5555/plugins | jq
```

### Logs

```bash
# Live logs
journalctl -u holod -f

# Errors only
journalctl -u holod -p err -f

# Export logs
journalctl -u holod --since "1 hour ago" > /tmp/holod.log
```

### Updates

```bash
# Automatic update script
update-holocene

# Manual update
cd /home/holocene/holocene
git pull
source venv/bin/activate
pip install -e . --upgrade
systemctl restart holod
```

### Backups

```bash
# On Proxmox host

# Snapshot
pct snapshot 100 pre-update

# Full backup
vzdump 100 --mode snapshot --compress zstd --storage local

# Restore from snapshot
pct rollback 100 pre-update
```

### Resource Monitoring

```bash
# Container stats
pct exec 100 -- top

# Memory usage
pct exec 100 -- free -h

# Disk usage
pct exec 100 -- df -h
```

---

## Troubleshooting

### Daemon Won't Start

```bash
# Check logs
journalctl -u holod -n 50

# Check permissions
ls -la /home/holocene/.holocene

# Test manually
su - holocene
cd holocene
source venv/bin/activate
holo daemon start --foreground
```

### API Not Responding

```bash
# Check if port is listening
ss -tlnp | grep 5555

# Check firewall
ufw status

# Test locally
curl http://localhost:5555/health
```

### mDNS Not Working

```bash
# Check Avahi
systemctl status avahi-daemon

# Test resolution
avahi-browse -a

# Force republish
systemctl restart avahi-daemon
```

### Network Issues

```bash
# Check connectivity
ping 8.8.8.8

# Check DNS
nslookup google.com

# Check routes
ip route show
```

### Database Locked

```bash
# Check for stale locks
fuser /home/holocene/.holocene/holocene.db

# Kill if needed
fuser -k /home/holocene/.holocene/holocene.db

# Restart daemon
systemctl restart holod
```

### High Memory Usage

```bash
# Check stats
pct exec 100 -- free -h

# Identify process
pct exec 100 -- ps aux --sort=-%mem | head

# Adjust container memory
pct set 100 --memory 4096
pct restart 100
```

---

## Useful Commands

### Container Management

```bash
# Enter container
pct enter 100

# Start/stop/restart
pct start 100
pct stop 100
pct restart 100

# Clone container
pct clone 100 101 --hostname holocene-test

# Destroy container
pct destroy 100
```

### Holocene Operations

```bash
# Inside container or via pct exec

# Daemon control
systemctl status holod
systemctl restart holod
journalctl -u holod -f

# CLI commands (from wmut with API client)
holo daemon status
holo daemon plugins
holo daemon logs
```

### Network Testing

```bash
# From wmut
ping holocene-rei.local
curl http://holocene-rei.local:5555/status
nmap -p 5555 holocene-rei.local

# From rei
pct exec 100 -- curl http://localhost:5555/health
```

---

## Architecture Summary

```
┌─────────────────────────────────────────────┐
│ Proxmox Host (rei)                          │
│                                             │
│  ┌────────────────────────────────────┐    │
│  │ LXC 100: holocene-rei              │    │
│  │                                    │    │
│  │  Services:                         │    │
│  │  - holod (systemd)                 │    │
│  │  - Flask API (:5555)               │    │
│  │  - Avahi (mDNS)                    │    │
│  │  - Tailscale (optional)            │    │
│  │  - cloudflared (optional)          │    │
│  │                                    │    │
│  │  Storage:                          │    │
│  │  - ~/.holocene/holocene.db         │    │
│  │  - ~/.config/holocene/config.yml   │    │
│  └────────────────────────────────────┘    │
└─────────────────────────────────────────────┘

Access Methods:
1. Local:     http://holocene-rei.local:5555
2. Tailscale: http://holocene-rei:5555
3. Cloudflare: https://holocene.yourdomain.com
```

---

## Security Notes

1. **Change default passwords** after deployment
2. **Restrict API access** via firewall if exposing publicly
3. **Use HTTPS** with Cloudflare Tunnel for external access
4. **Regular backups** with Proxmox snapshots
5. **Monitor logs** for unauthorized access
6. **Keep system updated**: `update-holocene`

---

## Next Steps

After deployment:

1. ✅ Configure API keys in config.yml
2. ✅ Test API from wmut: `curl http://holocene-rei.local:5555/status`
3. ✅ Set up Telegram bot for mobile (eunice)
4. ✅ Configure Cloudflare Tunnel for external access
5. ✅ Install Tailscale for secure remote access
6. ✅ Set up automated backups
7. ✅ Build balloc and dixie plugins!

---

## Support

- **GitHub**: https://github.com/endarthur/holocene
- **Issues**: https://github.com/endarthur/holocene/issues
- **Docs**: See `/docs` folder

---

**Happy deploying! 🚀**
