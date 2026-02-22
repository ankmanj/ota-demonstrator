# OTA Demonstrator - Hands-On Learning Roadmap (1-2 Years)

**Philosophy**: Build first, understand deeply second. Learn theory only when you need it to solve a real problem you're facing.

---

## 🎯 Learning Approach

### The Cycle (repeat for each milestone)
```
1. BUILD something tangible (2-3 days)
   ↓
2. BREAK it intentionally (1 day)
   ↓
3. STUDY why it broke (1-2 hours)
   ↓
4. FIX it with deeper understanding
   ↓
5. DOCUMENT what you learned
```

### Hands-On:Theory Ratio
- **80% hands-on**: Writing code, configuring systems, testing
- **20% theory**: Only when stuck or optimizing

---

## Phase 1: Backend Running (Week 1)
**Goal**: Get something visible working immediately

### 🔨 Hands-On (4-5 hours)
```bash
# Day 1 Morning: Start backend
./start.sh
# Play with hawkBit UI, create fake devices, explore MinIO

# Day 1 Afternoon: Break things on purpose
docker-compose stop postgres
# What happens to hawkBit? Why?

docker-compose stop mosquitto
# Try to connect a fake device

# Day 1 Evening: Fix and document
docker-compose restart postgres
# Write down what each service does
```

**Deliverable**: All services running + notes on what each does

### 📚 Theory (30 mins - ONLY after breaking things)
**Read only these specific sections when you're stuck:**
- Docker Compose networking (when MQTT won't connect)
- PostgreSQL basics (when hawkBit data is gone)
- MQTT pub/sub (when devices can't communicate)

**Learning Log Template**:
```markdown
## What I Built Today
- Started 6 Docker containers
- Accessed hawkBit UI
- Created test device

## What I Broke
- Stopped PostgreSQL -> hawkBit crashed
- Stopped MQTT -> devices can't connect

## What I Learned (theory)
- PostgreSQL stores all hawkBit state
- MQTT is pub/sub, not request/response
- Services need health checks

## Questions for Later
- How does hawkBit use RabbitMQ vs MQTT?
- Why do we need both MinIO and PostgreSQL?
```

---

## Phase 2: First Package Creation (Week 2)
**Goal**: Create something you can actually push to a device

### 🔨 Hands-On (8-10 hours)

**Day 1: Generate Keys**
```bash
# Build the key generation script
# Make it work
# Sign a test file
# Verify signature manually
# KEy generation happening using the openSSL RSA using the SHA256 hashes. 
# The files are signed using the private key locally and the target verfies the signature using the public key. 
# The target receives the file, Hashes the file using the same Sha256, decrypts the signature using the public to get the hash from the sender and verifies the receives file hash and decrypted hash.
```

**Day 2: Create Package**
```bash
# Write build-package.sh
# Create simple rootfs with:
#   - /etc/ota-demo/version.txt
#   - /usr/local/bin/hello.sh
# Build .swu package
# Upload to MinIO
```

**TODO: Signing Algorithm Comparison**
- [x] Create packages signed with different algorithms:
  - [x] RSA-4096 + SHA-256 (current)
  - [ ] RSA-4096 + SHA-512
  - [x] ECDSA P-256 + SHA-256
  - [x] Ed25519
- [x] Compare performance metrics:
  - [x] Key generation time
  - [ ] Signing time (needs larger file or iterations)
  - [ ] Verification time
  - [x] Signature size
- [ ] Test compatibility with SWUpdate on Raspberry Pi
- [ ] Document results in a comparison table

**Benchmark Results (Key Generation)**
| Algorithm | Key Generation Time |
|-----------|---------------------|
| RSA-4096  | 3.684s              |
| ECDSA P-256 | 1.653s            |
| Ed25519   | 1.433s              |

**Benchmark Results (Signature sizes)**
| Algorithm | Signature sizes |
|-----------|---------------------|
| RSA-4096  | 512 bytes              |
| ECDSA P-256 | 70            |
| Ed25519   | 64              |

> **Note:** Signing time differences were not noticeable due to small sw-description file size (~200 bytes). For accurate signing benchmarks, need to use larger files or run 1000+ iterations.

**Day 3: Break It**
```bash
# Try invalid signature
# Try corrupted package
# Try package without manifest
# Document what makes a valid package
```

**Deliverable**: Script that creates signed packages + upload script

### 📚 Theory (1 hour - when packages fail)
**Only read these when you hit these specific problems:**
- RSA cryptography basics (when signature verification fails)
- SWUpdate format (when package is rejected)
- File system hierarchy (when deciding where files go)

### 🎓 Deep Dive Exercise (optional, 2 hours)
**If you want to understand deeply:**
```bash
# Unpack an .swu file manually
tar -xf mypackage.swu

# Study sw-description file
cat sw-description

# Try modifying it
# Repack and see what breaks
```

---

## Phase 3: Raspberry Pi Setup (Week 3-4)
**Goal**: Make a real device accept OTA updates

### 🔨 Hands-On (12-15 hours)

**Weekend 1: Physical Setup**
```bash
# Flash SD card
# Boot Pi
# SSH in
# Install basic tools
# Take snapshot of working system

# THEN break it:
# Delete critical files
# Restore from backup
# Now you understand why we need A/B!
```

**Weekday: Partition Setup**

📖 **[Complete A/B Partitioning Guide](A-B-Partitioning-Setup.md)** - Comprehensive documentation with PlantUML diagrams covering:
- Partition creation using GParted
- Linux boot process with initramfs
- Busybox and system utilities
- Partition switching mechanism
- Complete A/B update flow

```bash
# Manually create second partition
# Mount it
# Copy root filesystem
# Try booting from it (will fail)
# Document why it failed

# Fix: Configure bootloader
# Now boot from partition B
# Document what U-Boot actually does
```

**Weekend 2: SWUpdate**
```bash
# Install SWUpdate
# Feed it a package (wrong format)
# Watch it fail
# Read error messages
# Fix package format
# Try again until it works
```

**Deliverable**: Pi that boots from either partition

### 📚 Theory (2-3 hours - spread across 2 weeks)
**Learn only when you encounter the problem:**
- Linux boot process (when boot fails)
- Partition tables (when fdisk confuses you)
- File systems (when choosing ext4 vs others)
- U-Boot basics (when configuring bootloader)

### 🔬 Experiments to Try
```bash
# Experiment 1: Boot flag
# Manually edit boot flag
# Reboot
# Watch which partition it uses

# Experiment 2: Kernel panic
# Boot to partition with broken init
# Watch watchdog reboot
# Document the recovery process

# Experiment 3: Health check
# Create failing health check
# Watch rollback happen
# This is your "aha!" moment
```

---

## Phase 4: First Real Update (Week 5)
**Goal**: Complete end-to-end OTA update

### 🔨 Hands-On (10-12 hours)

**Day 1-2: Update Agent**
```bash
# Write simple Python agent:
#   1. Connect to MQTT
#   2. Listen for updates
#   3. Download package
#   4. Verify signature
#   5. Call SWUpdate
#   6. Reboot

# Start simple - just print messages
# Add one feature at a time
# Test after each addition
```

**Day 3-4: First Update**
```bash
# Create package v1.0 (adds one file)
# Upload to MinIO
# Create campaign in hawkBit
# Watch logs on device
# See update happen!

# Then immediately:
# Create v1.1 with bug
# Watch it rollback
# THIS is the best learning moment
```

**Deliverable**: Working end-to-end update + one successful rollback

### 📚 Theory (1-2 hours - just-in-time)
**Only when you hit these issues:**
- MQTT QoS levels (when messages drop)
- Python asyncio (when agent blocks)
- Systemd services (when agent won't start on boot)

### 🎮 Challenge Exercises
```bash
# Challenge 1: Network drops
# Unplug ethernet during download
# Does it resume? Should it?
# Add resume capability

# Challenge 2: Power loss
# Kill power during update
# What state is system in?
# Add recovery logic

# Challenge 3: Signature bypass
# Try to install unsigned package
# Make sure it fails
# Document security model
```

---

## Phase 5-6: Multi-Device Fleet (Weeks 6-8)
**Goal**: Manage 3+ devices at once

### 🔨 Hands-On (15-20 hours)

**Setup**
```bash
# Week 1: Add second Pi
# Clone SD card
# Change device ID
# Register in hawkBit
# Do staged rollout to both

# Week 2: Add QEMU device
# Run QEMU with network
# Same update agent
# Now you have 3-device fleet

# Week 3: Chaos Engineering
# Update device 1: success
# Update device 2: force failure
# Update device 3: network drop
# Handle all three scenarios
```

**Deliverable**: 3+ devices with different update outcomes

### 📚 Theory (2 hours - when scaling)
**Only read when you face these:**
- Database indexing (when hawkBit slows down)
- MQTT scaling (when broker struggles)
- Load balancing (when planning 100+ devices)

### 🧪 Real-World Scenarios
```bash
# Scenario 1: Regional Rollout
# Device 1: US (fast network)
# Device 2: India (slow network)
# Device 3: Germany (medium)
# Optimize for each

# Scenario 2: Device Groups
# Group by hardware version
# Group by location
# Group by criticality
# Test targeting logic

# Scenario 3: Emergency Rollback
# Deploy bad update to all
# How fast can you rollback?
# Measure and optimize
```

---

## Phase 7-8: Security Hardening (Weeks 9-12)
**Goal**: Make it production-secure

### 🔨 Hands-On (20-25 hours)

**Week 1: Attack Your Own System**
```bash
# Attack 1: Man-in-the-Middle
# Intercept MQTT traffic
# Modify package during download
# Try to install malicious update
# Document what SHOULD fail

# Attack 2: Replay Attack
# Capture old update message
# Replay it
# Should device accept it? (NO!)

# Attack 3: Key Compromise
# Pretend private key is stolen
# How do you revoke it?
# Implement key rotation
```

**Week 2: Add TPM (if you have hardware)**
```bash
# Connect TPM module
# Store keys in TPM
# Try to extract keys (should fail)
# Measure boot integrity
# Document trust chain
```

**Week 3-4: Secure Boot**
```bash
# Enable secure boot on Pi
# Sign bootloader
# Sign kernel
# Try booting unsigned kernel (should fail)
# Document complete trust chain
```

**Deliverable**: Attack documentation + countermeasures implemented

### 📚 Theory (3-4 hours - when implementing)
**Only when you need to understand:**
- PKI and certificate chains (when doing mTLS)
- TPM architecture (when integrating hardware)
- Secure boot flow (when kernel won't boot)
- UNECE R156 requirements (when documenting compliance)

### 🛡️ Security Challenges
```bash
# Challenge 1: Zero Trust
# Assume everything is compromised
# Design system that still works
# Document threat model

# Challenge 2: Compliance Audit
# Pretend you're auditor
# Try to find vulnerabilities
# Document findings
# Fix them

# Challenge 3: Penetration Test
# Ask a friend to try breaking in
# Document their attempts
# Learn from failures
```

---

## Phase 9-10: Kubernetes & Scale (Weeks 13-18)
**Goal**: Handle 1000+ devices

### 🔨 Hands-On (30-35 hours)

**Weeks 1-2: Local K8s**
```bash
# Install K3s on laptop
# Convert docker-compose to K8s
# One service at a time
# Break things constantly
# Learn kubectl by debugging

# Deploy to cluster
# Scale hawkBit to 3 replicas
# Kill one pod
# Watch K8s recover
# THIS teaches HA better than any book
```

**Weeks 3-4: Production Deploy**
```bash
# Get cheap VPS ($5-10/month)
# Deploy to real cloud
# Point domain name at it
# Add TLS
# Make it public

# Then stress test:
# Simulate 100 devices
# Simulate 1000 devices
# Find bottlenecks
# Optimize
```

**Weeks 5-6: Advanced Features**
```bash
# Add Prometheus
# Add Grafana
# Add alerting
# Simulate outage
# Get paged
# Fix it
# Document incident
```

**Deliverable**: Public demo URL + load test results

### 📚 Theory (4-5 hours - when needed)
**Only when you face these issues:**
- Kubernetes architecture (when pods keep restarting)
- Service mesh (when considering Istio)
- Horizontal Pod Autoscaling (when load increases)
- Database replication (when PostgreSQL becomes bottleneck)

### 🚀 Performance Challenges
```bash
# Challenge 1: 1000 Devices
# Generate 1000 fake devices
# All poll for updates
# Measure response time
# Optimize until <100ms

# Challenge 2: Global Deploy
# Deploy to 3 regions
# Route users to nearest
# Measure latency
# Document CDN strategy

# Challenge 3: Cost Optimization
# Current monthly cost: $X
# Optimize to $X/2
# Without losing features
# Document every saving
```

---

## Phase 11-14: NVIDIA Integration (Weeks 19-28)
**Goal**: Make it NVIDIA-impressive

### 🔨 Hands-On (40-50 hours)

**Weeks 1-3: Jetson Platform**
```bash
# Buy Jetson Orin Nano ($499)
# OR rent in cloud
# Port everything to Jetson
# Document differences from Pi

# Add CUDA-based verification
# GPU-accelerated signature check
# Benchmark vs CPU
# Show 10x speedup in deck
```

**Weeks 4-5: ML Model Updates**
```bash
# Create simple CNN model
# Version 1: 90% accuracy
# Package as OTA update
# Deploy to Jetson
# Measure inference time

# Version 2: 95% accuracy
# OTA update the model
# A/B test performance
# Rollback if worse
# Document ML-OTA workflow
```

**Weeks 6-8: DRIVE Platform Alignment**
```bash
# Study NVIDIA DRIVE docs
# Align package format
# Align security model
# Create DRIVE-compatible demo
# Document mapping

# If possible: Deploy to DRIVE board
# If not: Simulate with docs
```

**Weeks 9-10: Edge AI Features**
```bash
# Add TensorRT optimization
# Add model quantization
# Add A/B testing for models
# Add performance telemetry
# Show real metrics in demo
```

**Deliverable**: Jetson-based demo + ML model OTA + DRIVE compatibility doc

### 📚 Theory (5-6 hours - when integrating)
**Only when you need it:**
- CUDA programming basics (when writing GPU verification)
- TensorRT optimization (when models are slow)
- DRIVE OS architecture (when aligning designs)
- Automotive AI deployment (when documenting approach)

### 🎯 NVIDIA-Specific Challenges
```bash
# Challenge 1: Vehicle Simulation
# Create mock vehicle data
# Update AI model based on data
# Show improvement over time
# Document before/after metrics

# Challenge 2: Safety-Critical Updates
# Designate one component "critical"
# Require extra validation
# Add redundancy
# Document safety case

# Challenge 3: Edge Computing
# Deploy model to edge
# Show bandwidth savings
# Compare vs cloud inference
# Document edge strategy
```

---

## Phase 15-20: Advanced & Unique Features (Weeks 29-52)
**Goal**: Add features that make you stand out

### 🔨 Choose 3-4 Projects That Excite You

#### Option A: Blockchain Audit Trail (6-8 weeks)
```bash
# Week 1-2: Basic blockchain
# Create simple chain
# Add update records
# Make it immutable

# Week 3-4: Smart contracts
# Deploy on test network
# Record updates on-chain
# Query history

# Week 5-6: Integration
# Auto-log all updates
# Create audit dashboard
# Show immutable history

# Week 7-8: Polish
# Optimize gas costs
# Add analytics
# Document use case
```

**Theory (2 hours)**: Basic blockchain concepts (only when writing smart contract)

#### Option B: ML-Based Failure Prediction (6-8 weeks)
```bash
# Week 1-2: Collect data
# Log all update attempts
# Label success/failure
# Export to CSV

# Week 3-4: Train model
# Use scikit-learn
# Predict failure probability
# Test accuracy

# Week 5-6: Integration
# Add to update pipeline
# Flag risky updates
# Prevent deployment

# Week 7-8: Dashboard
# Show predictions
# Show accuracy over time
# Document approach
```

**Theory (3 hours)**: ML basics (only when model doesn't converge)

#### Option C: V2X Update Sharing (8-10 weeks)
```bash
# Week 1-2: Simulate vehicles
# Create 10 virtual vehicles
# Position them in space
# Simulate movement

# Week 3-4: P2P protocol
# Vehicle-to-vehicle sharing
# Bandwidth optimization
# Verify security

# Week 5-6: Optimization
# Optimal sharing strategy
# Reduce cellular data 90%
# Benchmark vs traditional

# Week 7-8: Visualization
# Real-time map
# Show update spreading
# Measure efficiency

# Week 9-10: Polish
# Add animations
# Create demo video
# Document findings
```

**Theory (2 hours)**: P2P protocols (when designing sharing)

#### Option D: Container-Based Updates (6-8 weeks)
```bash
# Week 1-2: Docker on device
# Run containers on Pi
# Update container images
# A/B test containers

# Week 3-4: Orchestration
# Add k3s to device
# Deploy pods
# Update pods via OTA

# Week 5-6: Integration
# Mix traditional + container
# Update both types
# Show flexibility

# Week 7-8: Demo
# Show full-stack update
# OS + containers + models
# Document approach
```

**Theory (2 hours)**: Container internals (when debugging)

---

## Year 2: Mastery & Influence (Weeks 53-104)

### 🔨 Hands-On Projects (Choose Based on Interest)

**Quarter 1 (Weeks 53-65): Open Source**
```bash
# Contribute to hawkBit
# Submit bug fixes
# Add features
# Become known contributor

# Write MCP for Home Assistant
# Let HA users do OTA
# Create example automations
# Present at HA meetup
```

**Quarter 2 (Weeks 66-78): Content Creation**
```bash
# Write technical blog series
# "Building Production OTA in 2025"
# Post weekly
# Build audience

# Create YouTube tutorials
# Screen recordings with voice
# "OTA Update Series"
# 10-15 minute episodes
```

**Quarter 3 (Weeks 79-91): Conference Circuit**
```bash
# Submit to conferences
# Embedded Linux Conference
# Automotive Linux Summit
# Local meetups

# Prepare talks
# Practice delivery
# Get feedback
# Present
```

**Quarter 4 (Weeks 92-104): Job Hunting**
```bash
# Polish everything
# Update portfolio
# Record demo videos
# Prepare interview stories

# Apply to NVIDIA
# Use project in interviews
# Show passion through work
# Get offer!
```

### 📚 Theory (Ongoing - 2-3 hours/month)
**Stay current:**
- Read automotive OTA papers
- Follow NVIDIA blog
- Join automotive forums
- Attend webinars

---

## 📊 Progress Tracking

### Weekly Log Template
```markdown
# Week X

## Built This Week (80% of time)
- [List concrete things]

## Broke & Fixed (debugging)
- [What failed, how you fixed it]

## Learned (20% of time)
- [Theory learned while solving problems]

## Next Week Goals
- [3-5 concrete tasks]

## Blocker / Questions
- [Things you're stuck on]
```

### Monthly Review
```markdown
# Month X

## Demos I Can Show
- [Working features]

## Skills Acquired
- [Technical skills]

## Theory Gaps
- [Things I need to study]

## Pride Moments
- [Coolest achievement]
```

---

## 🎯 Learning Resources (Use Only When Stuck)

### When You Need Them, Not Before

**Docker Issues?**
→ Docker docs → Specific problem only

**Kubernetes Confusion?**
→ Official tutorials → Hands-on labs

**Linux Boot Problems?**
→ Arch Wiki → Boot process page

**Security Questions?**
→ OWASP guides → Specific topic

**NVIDIA Integration?**
→ NVIDIA docs → Specific platform

### Avoid These Traps
❌ "I need to learn K8s before I start" → NO!
✅ "My pod won't start, let me look that up" → YES!

❌ "Let me read this 500-page book first" → NO!
✅ "Let me search why this command failed" → YES!

❌ "I should understand everything before coding" → NO!
✅ "I'll understand it after I break it" → YES!

---

## 🚀 Your First Week (Detailed)

### Monday (2 hours)
```bash
# 09:00-09:30: Start backend
./start.sh

# 09:30-10:30: Explore UIs
# Click everything in hawkBit
# Upload random file to MinIO
# Send MQTT message manually

# 10:30-11:00: Break something
docker-compose stop redis
# What broke? Why?
```

### Tuesday (2 hours)
```bash
# Create first script
# generate-keys.sh
# Make it work
# Sign a test file
```

### Wednesday (2 hours)
```bash
# Build first package
# Even if it's just one file
# Upload to MinIO
# See it in hawkBit
```

### Thursday (2 hours)
```bash
# Start device simulator
# Python script
# Connect to MQTT
# Print messages
```

### Friday (2 hours)
```bash
# Connect simulator to hawkBit
# Make it poll for updates
# Download a package
# Simulate installation
```

### Weekend (4-6 hours)
```bash
# Commit everything
# Write README
# Document what works
# List what to do next week
```

**After Week 1**: You'll have working backend + simulator!

---

## 💡 Learning Principles

### 1. Build-Break-Fix
Best learning happens when YOU break it.

### 2. Just-In-Time Theory
Learn theory when you need it, not before.

### 3. Document Everything
Your future self will thank you.

### 4. Share Your Journey
Blog posts = proof you learned.

### 5. Fail Fast, Fail Often
Every error message teaches something.

---

## 🎓 Measure Your Progress

### Don't Measure By
❌ Pages read
❌ Videos watched
❌ Courses completed

### Measure By
✅ Working features
✅ Bugs fixed
✅ Real updates deployed
✅ Demos you can show
✅ Problems you solved

---

Ready to start? 

**Your first task is simple:**
```bash
./start.sh
```

Then tell me: **"Backend is running, help me create the key generation script"**

Let's build! 🚀