#!/bin/bash

# OTA Demonstrator - Quick Start Script
# This script helps you get the development environment up and running

set -e

echo "========================================="
echo "  OTA Demonstrator - Quick Start"
echo "========================================="
echo

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed${NC}"
    echo "Please install Docker from https://docs.docker.com/get-docker/"
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed${NC}"
    echo "Please install Docker Compose from https://docs.docker.com/compose/install/"
    exit 1
fi

echo -e "${GREEN}✓ Docker and Docker Compose are installed${NC}"
echo

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${YELLOW}Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ Created .env file${NC}"
    echo -e "${YELLOW}  You can customize it if needed${NC}"
else
    echo -e "${GREEN}✓ .env file exists${NC}"
fi
echo

# Create necessary directories
echo "Creating necessary directories..."
mkdir -p mosquitto/config mosquitto/data mosquitto/log
cp mosquitto.conf mosquitto/config/
echo -e "${GREEN}✓ Directories created${NC}"
echo

# Start services
echo "Starting OTA Demonstrator services..."
echo "This may take a few minutes on first run..."
echo

docker compose up -d

echo
echo "Waiting for services to be healthy..."
sleep 10

# Check service health
echo
echo "Checking service status..."
docker compose ps

echo
echo "========================================="
echo -e "${GREEN}  Services Started Successfully!${NC}"
echo "========================================="
echo
echo "Access your services:"
echo -e "${GREEN}hawkBit UI:${NC}       http://localhost:8080"
echo "                   Username: admin / Password: admin"
echo
echo -e "${GREEN}MinIO Console:${NC}    http://localhost:9001"
echo "                   Username: minioadmin / Password: minioadmin123"
echo
echo -e "${GREEN}RabbitMQ Console:${NC} http://localhost:15672"
echo "                   Username: admin / Password: admin123"
echo
echo -e "${GREEN}MQTT Broker:${NC}      mqtt://localhost:1883"
echo -e "${GREEN}Redis:${NC}            localhost:6379"
echo
echo "========================================="
echo "Useful Commands:"
echo "========================================="
echo
echo "View logs:         docker compose logs -f [service]"
echo "Stop services:     docker compose stop"
echo "Restart services:  docker compose restart"
echo "Clean up:          docker compose down -v"
echo
echo "Next steps:"
echo "1. Access hawkBit UI at http://localhost:8080"
echo "2. Create your first update package"
echo "3. Set up a test device"
echo
echo "For detailed instructions, see: docs/GETTING_STARTED.md"
echo

# Check if services are responding
echo "Testing service connectivity..."
echo

# Test hawkBit
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080 | grep -q "200\|302"; then
    echo -e "${GREEN}✓ hawkBit is responding${NC}"
else
    echo -e "${YELLOW}⚠ hawkBit may still be starting up...${NC}"
fi

# Test MinIO
if curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live | grep -q "200"; then
    echo -e "${GREEN}✓ MinIO is responding${NC}"
else
    echo -e "${YELLOW}⚠ MinIO may still be starting up...${NC}"
fi

echo
echo -e "${GREEN}Setup complete! Happy updating! 🚀${NC}"
