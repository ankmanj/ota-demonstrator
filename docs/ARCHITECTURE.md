# Architecture Documentation

## System Overview

The OTA Demonstrator implements a complete over-the-air update system suitable for automotive embedded devices. The architecture follows cloud-native patterns with microservices, message queuing, and distributed storage.

## Core Principles

### 1. Safety First
- **A/B Partitioning**: Dual-partition scheme ensures system always has a bootable backup
- **Atomic Updates**: Updates either complete fully or rollback automatically
- **Health Checks**: Post-update validation ensures system stability
- **Watchdog Integration**: Automatic rollback on system failures

### 2. Security by Design
- **Cryptographic Signing**: All packages signed with RSA-4096 keys
- **Chain of Trust**: From build system to device verification
- **Secure Communication**: TLS 1.3 for all network traffic
- **Key Management**: Centralized vault for secrets management

### 3. Scalability
- **Horizontal Scaling**: All services can scale independently
- **Queue-based Communication**: MQTT for asynchronous messaging
- **Distributed Storage**: S3-compatible object storage
- **Stateless Services**: Enable easy horizontal scaling

### 4. Observability
- **Metrics Collection**: Prometheus for time-series data
- **Centralized Logging**: Structured logs for debugging
- **Real-time Monitoring**: Grafana dashboards for visibility
- **Distributed Tracing**: Request flow tracking

## Component Details

### Backend Services

#### Eclipse hawkBit
- **Role**: Update campaign management and orchestration
- **Technology**: Java Spring Boot
- **Database**: PostgreSQL for persistence
- **API**: REST API for device communication
- **Features**: 
  - Campaign creation and management
  - Device registry and grouping
  - Rollout strategies (soft/forced)
  - Update scheduling

#### Custom API Layer (FastAPI)
- **Role**: Business logic and custom extensions
- **Technology**: Python FastAPI
- **Features**:
  - Custom authentication
  - Analytics and reporting
  - Integration with external systems
  - Custom rollout strategies

#### MinIO Storage
- **Role**: Update package storage
- **Technology**: S3-compatible object storage
- **Features**:
  - Distributed storage
  - Versioning support
  - Bandwidth optimization
  - High availability

#### MQTT Broker (Mosquitto)
- **Role**: Real-time device communication
- **Technology**: Eclipse Mosquitto
- **Features**:
  - Publish/Subscribe messaging
  - QoS levels (0, 1, 2)
  - TLS encryption
  - Authentication/Authorization

#### Signing Service
- **Role**: Package signing and verification
- **Technology**: Python + cryptography
- **Features**:
  - RSA signature generation
  - Key rotation support
  - Verification API
  - Audit logging

### Edge Components

#### Update Client (SWUpdate/RAUC)
- **Role**: Package installation on device
- **Technology**: C/C++ embedded software
- **Features**:
  - Atomic updates
  - Rollback capability
  - Pre/post-install scripts
  - Multiple image types support

#### Bootloader (U-Boot)
- **Role**: Boot partition selection
- **Technology**: U-Boot or UEFI
- **Features**:
  - Boot flag management
  - Automatic failover
  - Secure boot support
  - Recovery mode

#### Telemetry Agent
- **Role**: Device status reporting
- **Technology**: Python/Rust
- **Features**:
  - Real-time status updates
  - Metrics collection
  - Log aggregation
  - Health monitoring

## Update Flow

### 1. Package Preparation
```
Developer → CI/CD → Build System → Signing Service → Storage
```
- Code changes committed to Git
- CI/CD pipeline triggers build
- Package created with manifest
- Cryptographic signature generated
- Uploaded to MinIO storage

### 2. Campaign Creation
```
Admin → Dashboard → hawkBit → Database
```
- Admin creates update campaign
- Defines target device groups
- Sets rollout strategy (e.g., 10% → 50% → 100%)
- Schedules deployment window

### 3. Device Discovery
```
hawkBit → MQTT → Device → Update Check
```
- Device periodically polls for updates
- hawkBit checks device eligibility
- Update notification sent via MQTT
- Device retrieves update metadata

### 4. Download & Verification
```
Device → MinIO → Download → Verify Signature
```
- Device downloads package from MinIO
- Verifies SHA-256 hash
- Validates cryptographic signature
- Checks storage space availability

### 5. Installation
```
Device → Mount Partition B → Extract → Install
```
- Standby partition mounted
- Package extracted and validated
- Files written to partition B
- Boot flag set to partition B

### 6. Activation
```
Device → Reboot → Boot Partition B → Health Check
```
- Device reboots
- Bootloader reads boot flag
- Boots from partition B
- Runs health checks

### 7. Verification
```
Health Check → Pass/Fail → Commit/Rollback
```
**Success Path:**
- Health checks pass
- Boot flag committed permanently
- Status reported to backend
- Partition A marked for cleanup

**Failure Path:**
- Health check fails or watchdog timeout
- Boot flag reverted
- Automatic reboot to partition A
- Failure reported to backend

## Security Architecture

### Key Management
```
HashiCorp Vault (Master)
    ↓
Signing Keys (RSA-4096)
    ↓
Package Signatures
    ↓
Device Verification
```

### Trust Chain
1. **Build System**: Trusted environment for package creation
2. **Signing Service**: Isolated service with access to private keys
3. **Package Storage**: Signed packages stored immutably
4. **Device Verification**: Public key pre-installed on device
5. **Secure Boot**: Hardware-level verification (optional)

### Communication Security
- **TLS 1.3**: All network communications encrypted
- **Certificate Pinning**: Devices trust specific CA certificates
- **Mutual TLS**: Optional client certificate authentication
- **Token-based Auth**: JWT tokens for API access

## Deployment Models

### Development (Docker Compose)
- Single-host deployment
- All services in containers
- Shared Docker network
- Local volumes for persistence
- Suitable for: Development, testing, demos

### Production (Kubernetes)
- Multi-node cluster
- High availability services
- Persistent volume claims
- Ingress controllers for routing
- Auto-scaling capabilities
- Suitable for: Production deployments, large fleets

## Scalability Considerations

### Horizontal Scaling
- **API Layer**: Scale based on request load
- **hawkBit**: Scale based on device count
- **MQTT Broker**: Clustered for high throughput
- **Storage**: Distributed MinIO cluster

### Performance Optimization
- **CDN Integration**: Reduce download latency
- **Delta Updates**: Minimize bandwidth usage
- **Caching**: Redis for frequently accessed data
- **Database Indexing**: Optimize query performance

## Monitoring & Observability

### Metrics
- Device online/offline status
- Update success/failure rates
- Download speeds and bandwidth
- System resource utilization
- Campaign progress tracking

### Alerting
- Update failures exceeding threshold
- Device connectivity issues
- Storage capacity warnings
- Security incidents

### Logging
- Structured JSON logs
- Centralized log aggregation
- Log retention policies
- Search and analysis tools

## Disaster Recovery

### Backup Strategy
- Database backups (daily)
- Configuration backups
- Key backup in vault
- Package storage redundancy

### Recovery Procedures
- Database restoration
- Service redeployment
- Device re-registration
- Campaign state recovery

## Future Enhancements

### Planned Features
1. **Advanced Analytics**: ML-based failure prediction
2. **Multi-region**: Global deployment support
3. **Compliance**: UNECE R156/R155 compliance reporting
4. **Edge Computing**: Local update servers for bandwidth optimization
5. **Container Updates**: Support for containerized applications

### Research Areas
- **Blockchain**: Immutable audit trail
- **AI/ML**: Predictive maintenance
- **Edge ML**: On-device intelligence updates
- **Quantum-safe**: Post-quantum cryptography

## References

- [Eclipse hawkBit Documentation](https://www.eclipse.org/hawkbit/)
- [SWUpdate Documentation](https://sbabic.github.io/swupdate/)
- [RAUC Documentation](https://rauc.readthedocs.io/)
- [UNECE WP.29 Regulations](https://unece.org/transport/vehicle-regulations)
- [AUTOSAR Specification](https://www.autosar.org/)
