# Infrastructure Setup

This directory contains the Docker Compose configuration for running the OTA Demonstrator backend services locally.

## Quick Start

```bash
# 1. Make sure you're in the infrastructure/docker directory
cd infrastructure/docker

# 2. Run the startup script
./start.sh

# 3. Access the services (see URLs below)
```

## Services

### hawkBit Update Server
- **URL**: http://localhost:8080
- **Username**: `admin`
- **Password**: `admin`
- **Purpose**: Update campaign management and device orchestration

### MinIO Object Storage
- **Console URL**: http://localhost:9001
- **API URL**: http://localhost:9000
- **Username**: `minioadmin`
- **Password**: `minioadmin123`
- **Purpose**: Storage for update packages
- **Buckets**:
  - `updates` - Update package files (.swu)
  - `signatures` - Package signatures

### RabbitMQ Message Broker
- **Console URL**: http://localhost:15672
- **AMQP Port**: 5672
- **Username**: `admin`
- **Password**: `admin123`
- **Purpose**: Internal messaging for hawkBit

### MQTT Broker (Mosquitto)
- **TCP Port**: 1883 (unencrypted, for development)
- **TLS Port**: 8883 (for production, requires certificates)
- **WebSocket Port**: 9001
- **Purpose**: Real-time device communication

### PostgreSQL Database
- **Port**: 5432
- **Database**: `hawkbit`
- **Username**: `hawkbit`
- **Password**: `hawkbit123`
- **Purpose**: Persistent storage for hawkBit

### Redis Cache
- **Port**: 6379
- **Purpose**: Session storage and caching

## Manual Setup

If you prefer not to use the start script:

```bash
# 1. Copy environment file
cp .env.example .env

# 2. Create directories
mkdir -p mosquitto/config mosquitto/data mosquitto/log
cp mosquitto.conf mosquitto/config/

# 3. Start services
docker-compose up -d

# 4. Check status
docker-compose ps

# 5. View logs
docker-compose logs -f
```

## Useful Commands

### Managing Services

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose stop

# Restart a specific service
docker-compose restart hawkbit

# View logs (all services)
docker-compose logs -f

# View logs (specific service)
docker-compose logs -f hawkbit

# Check service status
docker-compose ps

# Execute command in container
docker-compose exec hawkbit /bin/bash
```

### Cleanup

```bash
# Stop and remove containers (keeps data)
docker-compose down

# Stop and remove everything including volumes (DELETES ALL DATA!)
docker-compose down -v

# Remove unused images
docker system prune -a
```

## Troubleshooting

### Services won't start

```bash
# Check if ports are already in use
sudo netstat -tulpn | grep -E '8080|9000|9001|5432|1883|6379'

# Check Docker daemon
sudo systemctl status docker

# View detailed logs
docker-compose logs
```

### hawkBit not accessible

```bash
# Wait for initialization (can take 1-2 minutes on first start)
docker-compose logs hawkbit

# Check if PostgreSQL is ready
docker-compose exec postgres pg_isready

# Restart hawkBit
docker-compose restart hawkbit
```

### MinIO buckets not created

```bash
# Check minio-init logs
docker-compose logs minio-init

# Manually create buckets
docker-compose exec minio-client mc alias set local http://minio:9000 minioadmin minioadmin123
docker-compose exec minio-client mc mb local/updates
docker-compose exec minio-client mc mb local/signatures
```

### MQTT connection issues

```bash
# Test MQTT connectivity
mosquitto_sub -h localhost -p 1883 -t test

# Check Mosquitto logs
docker-compose logs mosquitto

# Verify configuration
docker-compose exec mosquitto cat /mosquitto/config/mosquitto.conf
```

## Configuration

### Environment Variables

Edit `.env` to customize:

```bash
# Database credentials
POSTGRES_PASSWORD=your_secure_password

# MinIO credentials  
MINIO_ROOT_PASSWORD=your_secure_password

# RabbitMQ credentials
RABBITMQ_PASSWORD=your_secure_password
```

### Resource Limits

Edit `docker-compose.yml` to add resource constraints:

```yaml
services:
  hawkbit:
    # ... existing config ...
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '1.0'
          memory: 1G
```

## Monitoring (Optional)

To enable Prometheus and Grafana:

1. Uncomment the `prometheus` and `grafana` services in `docker-compose.yml`
2. Create configuration files:
   ```bash
   mkdir -p prometheus grafana/dashboards grafana/datasources
   ```
3. Restart services:
   ```bash
   docker-compose up -d
   ```

Access Grafana at http://localhost:3001 (admin/admin123)

## Production Considerations

Before deploying to production:

1. **Change all default passwords**
2. **Enable TLS for MQTT** (uncomment TLS config in mosquitto.conf)
3. **Use proper secrets management** (e.g., Docker secrets)
4. **Set resource limits** for all containers
5. **Configure backups** for PostgreSQL and MinIO
6. **Use external storage** for volumes (not local)
7. **Enable authentication** for all services
8. **Set up monitoring** and alerting
9. **Use Kubernetes** for scalability (see infrastructure/kubernetes/)

## Next Steps

1. ✅ Services running
2. 📦 Create your first update package (see scripts/build-package.sh)
3. 🔐 Generate signing keys (see scripts/generate-keys.sh)
4. 🤖 Set up a test device (see device/setup/)
5. 🚀 Deploy your first update!

For more details, see the main documentation in `/docs/GETTING_STARTED.md`
