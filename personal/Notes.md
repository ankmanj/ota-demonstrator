# OTA Demonstrator Services

## Overview

This document describes the services used in the OTA demonstrator and their roles.

---

## Services

### 1. hawkBit

Central update server for update management. Handles campaigns, rollouts, and device targeting.

### 2. PostgreSQL

Main persistent database used to store:
- Software versions
- Device registries
- Update actions and history

### 3. Redis

In-memory cache layer that complements PostgreSQL. Speeds up frequently accessed data by caching queries in RAM instead of hitting disk.

### 4. RabbitMQ

Internal message broker for hawkBit. Handles asynchronous communication between hawkBit components.

### 5. MinIO

S3-compatible object storage for update packages. Benefits:
- Stores `.swu` update files and signatures
- Easy migration path to AWS S3 or other cloud providers
- Standard S3 API compatibility

### 6. MinIO Client (mc)

One-time setup tool that creates buckets when MinIO starts. Without this, bucket creation would need to be done manually via the web UI.

### 7. Mosquitto Broker

MQTT broker for communication between OTA components and devices. Used for:
- Update notifications to devices
- Status reporting from devices

> **Note:** RabbitMQ can also perform MQTT brokering, but it's heavyweight for this purpose as it performs MQTT ↔ AMQP ↔ MQTT translation internally.