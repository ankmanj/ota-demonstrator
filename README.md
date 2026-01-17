# OTA Demonstrator

A production-grade Over-The-Air (OTA) update system demonstrator built for showcasing automotive software update capabilities. This project implements a complete OTA infrastructure with fleet management, secure updates, A/B partitioning, and automatic rollback.

## 🎯 Project Goals

- Demonstrate real-world OTA update workflows for embedded automotive systems
- Showcase cloud-native backend architecture with Kubernetes deployment
- Implement secure update mechanisms with cryptographic signing
- Provide fleet management capabilities with staged rollouts
- Enable automatic rollback on update failures

## 🏗️ Architecture Overview

This system consists of three main components:

### Backend Infrastructure
- **Update Server**: Eclipse hawkBit for campaign management
- **API Layer**: FastAPI for custom business logic
- **Storage**: MinIO (S3-compatible) for update packages
- **Database**: PostgreSQL for device registry and metadata
- **Messaging**: MQTT broker for real-time device communication
- **Security**: HashiCorp Vault for key management and signing service

### Edge Devices
- **Update Client**: SWUpdate/RAUC for package installation
- **Partitioning**: A/B partition scheme for safe updates
- **Bootloader**: U-Boot/UEFI with boot flag management
- **Telemetry**: Status reporting via MQTT
- **Target Platforms**: Raspberry Pi 4, NVIDIA Jetson, or QEMU

### Monitoring & Management
- **Dashboard**: React-based web interface
- **Metrics**: Prometheus for observability
- **Visualization**: Grafana dashboards
- **Integration**: Home Assistant compatibility

## 📊 Architecture Diagrams

Detailed architecture diagrams are available in the `docs/architecture/` directory:

- **[System Architecture](docs/architecture/ota-architecture.mermaid)**: Complete system overview with all components
- **[Update Flow](docs/architecture/ota-sequence-flow.mermaid)**: Detailed sequence diagram of update process
- **[Deployment Architecture](docs/architecture/ota-deployment.mermaid)**: Docker Compose and Kubernetes deployment models

To view these diagrams:
1. Use [Mermaid Live Editor](https://mermaid.live)
2. Install VS Code with Mermaid extension
3. View directly on GitHub (native Mermaid support)

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose (v2.0+)
- Git
- At least one device (Raspberry Pi 4 or similar) for testing
- Optional: Kubernetes cluster for production deployment

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/ankmanj/ota-demonstrator.git
cd ota-demonstrator

# Start the backend services
docker-compose up -d

# Access the services
# - hawkBit UI: http://localhost:8080 (admin/admin)
# - API: http://localhost:8000
# - Dashboard: http://localhost:3000
# - MinIO: http://localhost:9001 (minioadmin/minioadmin)
```

### Device Setup

```bash
# On your Raspberry Pi or target device
# 1. Set up A/B partitions
sudo ./scripts/setup-partitions.sh

# 2. Install SWUpdate
sudo apt-get install swupdate

# 3. Configure the update agent
sudo cp configs/device-config.yaml /etc/ota/config.yaml
sudo vim /etc/ota/config.yaml  # Edit with your server URL

# 4. Start the update agent
sudo systemctl enable ota-agent
sudo systemctl start ota-agent
```

## 🔧 Development

### Project Structure

```
ota-demonstrator/
├── docs/                    # Documentation and diagrams
│   └── architecture/        # Architecture diagrams
├── backend/                 # Backend services
│   ├── api/                # FastAPI application
│   ├── signing-service/    # Package signing service
│   └── web/                # React dashboard
├── device/                  # Edge device components
│   ├── update-agent/       # Update client
│   └── configs/            # Device configurations
├── infrastructure/          # Deployment configs
│   ├── docker/             # Docker Compose files
│   └── kubernetes/         # K8s manifests
├── packages/               # Example update packages
└── scripts/                # Utility scripts
```

### Building Update Packages

```bash
# Create a new update package
./scripts/build-package.sh --version 2.0 --type full

# Create a delta update
./scripts/build-package.sh --version 2.0 --type delta --base-version 1.5

# Sign the package
./scripts/sign-package.sh packages/update-2.0.swu
```

### Running Tests

```bash
# Backend tests
cd backend/api
pytest

# Integration tests
cd tests/integration
pytest test_update_flow.py

# Simulate device updates
./scripts/test-device-update.sh
```

## 📦 Deployment

### Docker Compose (Development)

```bash
docker-compose -f infrastructure/docker/docker-compose.yml up -d
```

### Kubernetes (Production)

```bash
# Create namespace
kubectl create namespace ota-system

# Deploy services
kubectl apply -f infrastructure/kubernetes/

# Check status
kubectl get pods -n ota-system
```

## 🔐 Security Features

- **Cryptographic Signing**: All packages signed with RSA-4096
- **Signature Verification**: Device-side verification before installation
- **Secure Boot**: Optional TPM integration for hardware root of trust
- **TLS Encryption**: All communications encrypted in transit
- **Key Management**: HashiCorp Vault for secure key storage
- **Certificate-based Auth**: Mutual TLS for device authentication

## 🎯 Use Cases

### Automotive OTA Updates
- ECU firmware updates
- Infotainment system updates
- ADAS software updates
- Complete vehicle software stack updates

### Fleet Management
- Campaign creation and management
- Staged rollouts (canary deployments)
- Region-based targeting
- Vehicle group management

### Safety & Compliance
- Automatic rollback on failure
- Update verification and validation
- Audit trail and compliance reporting
- State machine for update lifecycle

## 📈 Features

- ✅ A/B partition updates with automatic rollback
- ✅ Delta updates for bandwidth efficiency
- ✅ Staged rollout campaigns
- ✅ Real-time device status monitoring
- ✅ Package signing and verification
- ✅ Fleet management dashboard
- ✅ MQTT-based real-time communication
- ✅ Prometheus metrics and Grafana dashboards
- ✅ Multi-device support (RPi, Jetson, QEMU)
- ✅ Docker Compose and Kubernetes deployment

## 🛣️ Roadmap

### Phase 1 - MVP (Current)
- [x] Basic update server setup
- [x] Single device update flow
- [x] A/B partition management
- [x] Web dashboard

### Phase 2 - Production Features
- [ ] Fleet management (multiple devices)
- [ ] Staged rollouts
- [ ] Delta update generation
- [ ] Campaign management UI
- [ ] Enhanced telemetry

### Phase 3 - Advanced
- [ ] Hardware security integration (TPM)
- [ ] Multi-region deployment
- [ ] Compliance reporting
- [ ] Advanced analytics

## 🤝 Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Eclipse hawkBit**: Update server framework
- **SWUpdate**: Reliable embedded software update mechanism
- **RAUC**: Robust Auto-Update Controller

## 📧 Contact

**Ankith Manjunath**  
Automotive Software Engineer  
GitHub: [@ankmanj](https://github.com/ankmanj)

---

*Built with ❤️ for the automotive software community*
