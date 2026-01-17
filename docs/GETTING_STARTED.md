# Getting Started Guide

This guide will help you set up the OTA Demonstrator system from scratch.

## Prerequisites

### Hardware Requirements
- **Development Machine**: 8GB+ RAM, 50GB+ disk space
- **Test Device**: Raspberry Pi 4 (4GB+) with 32GB+ SD card, or NVIDIA Jetson Nano

### Software Requirements
- **Operating System**: Linux (Ubuntu 22.04+) or macOS
- **Docker**: Docker Engine 20.10+ and Docker Compose v2.0+
- **Git**: Version control
- **Python**: 3.10+ (for development)
- **Node.js**: 18+ (for web dashboard development)

### Optional
- **Kubernetes**: Minikube or K3s for local K8s testing
- **VS Code**: With Docker and Mermaid extensions

## Installation Steps

### 1. Clone the Repository

```bash
git clone https://github.com/ankmanj/ota-demonstrator.git
cd ota-demonstrator
```

### 2. Start Backend Services

```bash
# Navigate to infrastructure directory
cd infrastructure/docker

# Start all services
docker-compose up -d

# Verify services are running
docker-compose ps

# Expected output:
# hawkbit       - running on port 8080
# mosquitto     - running on ports 1883, 8883
# minio         - running on ports 9000, 9001
# postgres      - running on port 5432
# redis         - running on port 6379
```

### 3. Access the Services

#### hawkBit Management UI
- URL: http://localhost:8080
- Username: `admin`
- Password: `admin`

#### MinIO Console
- URL: http://localhost:9001
- Username: `minioadmin`
- Password: `minioadmin`

#### API Documentation
- URL: http://localhost:8000/docs
- Interactive Swagger UI for API testing

### 4. Initialize the System

```bash
# Run initialization script
./scripts/init-system.sh

# This will:
# - Create default device groups
# - Set up initial distribution sets
# - Configure MQTT topics
# - Generate signing keys
```

### 5. Configure Your First Device

#### On Raspberry Pi

```bash
# 1. Flash SD card with Raspberry Pi OS (64-bit)
# 2. Boot the Pi and SSH into it

# 3. Install required packages
sudo apt-get update
sudo apt-get install -y swupdate python3-pip git

# 4. Clone device configuration
git clone https://github.com/ankmanj/ota-demonstrator.git
cd ota-demonstrator/device

# 5. Run device setup script
sudo ./setup-device.sh

# 6. Configure device settings
sudo nano /etc/ota/config.yaml

# Update these values:
# server_url: "http://YOUR_SERVER_IP:8080"
# mqtt_broker: "YOUR_SERVER_IP"
# device_id: "rpi-001"

# 7. Start the update agent
sudo systemctl enable ota-agent
sudo systemctl start ota-agent

# 8. Check status
sudo systemctl status ota-agent
```

#### Verify Device Registration

```bash
# On your development machine
# Check if device appears in hawkBit
curl http://localhost:8080/rest/v1/targets | jq

# You should see your device listed
```

## Creating Your First Update

### 1. Prepare Update Content

```bash
cd packages/examples

# Create a simple update package
mkdir -p rootfs/etc/ota-demo
echo "version=2.0" > rootfs/etc/ota-demo/version.txt
echo "Hello from OTA Update v2.0!" > rootfs/etc/ota-demo/message.txt
```

### 2. Build the Update Package

```bash
# Use the build script
./scripts/build-package.sh \
  --name "demo-update" \
  --version "2.0.0" \
  --type "application" \
  --rootfs packages/examples/rootfs

# Output: packages/demo-update-2.0.0.swu
```

### 3. Sign the Package

```bash
# Sign with your private key
./scripts/sign-package.sh packages/demo-update-2.0.0.swu

# This creates: packages/demo-update-2.0.0.swu.sig
```

### 4. Upload to hawkBit

```bash
# Upload via API
./scripts/upload-package.sh \
  --file packages/demo-update-2.0.0.swu \
  --name "Demo Update" \
  --version "2.0.0"

# Or upload via Web UI:
# 1. Go to http://localhost:8080
# 2. Navigate to Upload → Software Module
# 3. Upload the .swu file
```

### 5. Create Update Campaign

#### Via Web UI:
1. Go to **Distributions** → **Create Distribution**
2. Name: "Demo Update v2.0"
3. Add Software Module: "Demo Update 2.0.0"
4. Save

#### Via API:
```bash
curl -X POST http://localhost:8080/rest/v1/distributionsets \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{
    "name": "Demo Update v2.0",
    "version": "2.0.0",
    "type": "app",
    "modules": [
      {"id": 1}
    ]
  }'
```

### 6. Assign to Devices

```bash
# Assign to your test device
curl -X POST http://localhost:8080/rest/v1/targetFilters \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{
    "name": "Test Device Update",
    "query": "name==rpi-001"
  }'

# Create rollout
curl -X POST http://localhost:8080/rest/v1/rollouts \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{
    "name": "Deploy Demo v2.0",
    "distributionSetId": 1,
    "targetFilterQuery": "name==rpi-001",
    "type": "forced"
  }'
```

### 7. Monitor the Update

```bash
# On your device, watch the logs
sudo journalctl -u ota-agent -f

# Expected log sequence:
# - Update available notification
# - Download started
# - Signature verification
# - Installation to partition B
# - Reboot scheduled
# - Health check passed
# - Update confirmed
```

### 8. Verify Success

```bash
# SSH to your device
ssh pi@YOUR_DEVICE_IP

# Check the new version
cat /etc/ota-demo/version.txt
# Should show: version=2.0

cat /etc/ota-demo/message.txt
# Should show: Hello from OTA Update v2.0!

# Check update status
sudo ota-agent status
```

## Testing Rollback

### Simulate Update Failure

```bash
# Create a "bad" update that will fail health checks
cd packages/examples
mkdir -p rootfs-bad/usr/local/bin

# Create a script that exits with error
cat > rootfs-bad/usr/local/bin/health-check.sh << 'EOF'
#!/bin/bash
echo "Simulating health check failure"
exit 1
EOF
chmod +x rootfs-bad/usr/local/bin/health-check.sh

# Build bad package
./scripts/build-package.sh \
  --name "bad-update" \
  --version "3.0.0" \
  --type "application" \
  --rootfs packages/examples/rootfs-bad

# Upload and deploy...
```

### Expected Behavior

```
1. Device downloads update
2. Installs to partition B
3. Reboots to partition B
4. Health check fails
5. Watchdog triggers
6. Automatic reboot
7. Bootloader boots partition A
8. Device reports failure
9. System stable on previous version
```

## Advanced Configuration

### Enable TLS for MQTT

```bash
# Generate certificates
./scripts/generate-certs.sh

# Update docker-compose.yml
# Add certificate volumes to mosquitto service

# Update device configuration
# Add ca_cert, client_cert, client_key paths
```

### Configure Prometheus Monitoring

```bash
# Start Prometheus and Grafana
docker-compose -f infrastructure/docker/monitoring.yml up -d

# Access Grafana: http://localhost:3001
# Username: admin
# Password: admin

# Import dashboard from: dashboards/ota-overview.json
```

### Set Up Staged Rollout

```yaml
# In hawkBit, create rollout with stages:
stages:
  - name: "Canary"
    targetPercentage: 10
    successThreshold: 95
    
  - name: "Gradual"
    targetPercentage: 50
    successThreshold: 98
    
  - name: "Full"
    targetPercentage: 100
    successThreshold: 98
```

## Troubleshooting

### Device Not Appearing in hawkBit

```bash
# Check device logs
sudo journalctl -u ota-agent -n 50

# Common issues:
# 1. Wrong server URL in config
# 2. Network connectivity
# 3. MQTT broker not reachable

# Test connectivity
curl http://YOUR_SERVER:8080/rest/v1/system/info
mosquitto_pub -h YOUR_SERVER -t test -m "hello"
```

### Update Download Fails

```bash
# Check MinIO access
curl http://localhost:9000/health/live

# Check device network
ping YOUR_SERVER_IP

# Verify package exists
mc ls local/updates/
```

### Update Installs but Doesn't Boot

```bash
# Connect serial console to device
# Check bootloader logs

# Common issues:
# 1. Corrupted partition
# 2. Wrong partition UUID
# 3. Boot flag not set correctly

# Manual recovery:
# Boot from rescue SD card
# Mount partitions
# Verify file integrity
```

## Next Steps

- Read the [Architecture Documentation](ARCHITECTURE.md)
- Explore [API Documentation](API.md)
- Set up [Kubernetes Deployment](KUBERNETES.md)
- Configure [CI/CD Pipeline](CICD.md)

## Getting Help

- **GitHub Issues**: Report bugs or request features
- **Discussions**: Ask questions and share ideas
- **Documentation**: Check the `docs/` directory

## Quick Reference

### Useful Commands

```bash
# View all services status
docker-compose ps

# View logs
docker-compose logs -f hawkbit

# Restart a service
docker-compose restart mosquitto

# Clean up everything
docker-compose down -v

# Rebuild after code changes
docker-compose up -d --build

# Device status check
curl http://localhost:8080/rest/v1/targets/rpi-001 -u admin:admin

# Create test device
curl -X POST http://localhost:8080/rest/v1/targets \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d '{"controllerId":"test-001","name":"Test Device"}'
```

### File Locations

```
Configuration:
  - Backend: infrastructure/docker/.env
  - Device: /etc/ota/config.yaml
  - Keys: /var/lib/ota/keys/

Logs:
  - Backend: docker-compose logs
  - Device: /var/log/ota-agent.log
  
Data:
  - Packages: MinIO bucket 'updates'
  - Database: PostgreSQL 'hawkbit'
```

---

Happy updating! 🚀
