#!/bin/bash
# install_aiinabox.sh
# Unified installation script for AI in a Box.

set -e

echo "=== AI in a Box Unified Installation ==="

######################################
# 0.5. Ensure Docker daemon is running
######################################
# If Docker is installed but not running, this resolves "Cannot connect to the Docker daemon" errors.
function ensure_docker_running() {
    if ! sudo systemctl is-active --quiet docker; then
        echo "Docker daemon is not running. Attempting to start Docker..."
        sudo systemctl start docker
        sleep 3
    fi

    # Double-check if it started
    if ! sudo systemctl is-active --quiet docker; then
        echo "ERROR: Docker service is not running, and we cannot start it."
        echo "Check 'sudo systemctl status docker' for more info."
        exit 1
    fi
}

######################################
# 1. Install Docker (if needed)
######################################
echo "Checking for Docker..."
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. You may need to log out and back in for group changes to take effect."
else
    echo "Docker is already installed."
fi

# Make sure Docker is running now that it’s installed
ensure_docker_running

######################################
# 2. Install Docker Compose Plugin (v2)
######################################
echo "Checking for Docker Compose plugin..."
if ! docker compose version &> /dev/null; then
    echo "Docker Compose plugin not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
else
    echo "Docker Compose plugin is installed."
fi

######################################
# 3. Swarm Setup: Manager or Worker?
######################################
read -p "Is this the swarm manager node? (y/n): " is_manager
if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    echo "This node will act as the swarm manager."
    # Use 'sudo docker info' in case user isn't in the docker group
    if ! sudo docker info 2>/dev/null | grep -q "Swarm: active"; then
        IP=$(hostname -I | awk '{print $1}')
        echo "Initializing Docker Swarm with advertise address: $IP"
        sudo docker swarm init --advertise-addr "$IP"
    else
        echo "Swarm is already active on this node."
    fi
else
    echo "This node will join an existing swarm as a worker."
    read -p "Enter the manager node IP: " manager_ip
    read -p "Enter the swarm join token: " join_token
    sudo docker swarm join --token "$join_token" "$manager_ip:2377"
fi

######################################
# 4. Label Node Based on Hardware Architecture
######################################
NODE_ID=$(sudo docker info -f '{{.Swarm.NodeID}}')
ARCH=$(uname -m)

if [[ "$ARCH" == "armv7l" || "$ARCH" == "aarch64" ]]; then
    echo "Detected Raspberry Pi architecture ($ARCH). Labeling node as hardware=raspberrypi."
    sudo docker node update --label-add hardware=raspberrypi "$NODE_ID"
else
    echo "Detected architecture ($ARCH) (assumed Linux server). Labeling node as hardware=server."
    sudo docker node update --label-add hardware=server "$NODE_ID"
fi

######################################
# 4.5 GPU Setup (only on Linux server)
######################################
if [[ "$ARCH" != "armv7l" && "$ARCH" != "aarch64" ]]; then
    # Check if NVIDIA drivers (nvidia-smi) are installed
    if command -v nvidia-smi &> /dev/null; then
        echo "NVIDIA GPU detected (nvidia-smi found)."
        read -p "Do you want to configure the GPU for Docker Swarm? (y/n): " setup_gpu
        if [[ "$setup_gpu" =~ ^[Yy]$ ]]; then
            DOCKER_DAEMON="/etc/docker/daemon.json"
            echo "Configuring node-generic-resources for NVIDIA GPU in $DOCKER_DAEMON..."

            if ! command -v jq &> /dev/null; then
              echo "Installing jq for JSON manipulation..."
              sudo apt-get update
              sudo apt-get install -y jq
            fi

            # If daemon.json doesn't exist, create an empty JSON object
            if [ ! -f "$DOCKER_DAEMON" ]; then
                echo "{}" | sudo tee "$DOCKER_DAEMON" > /dev/null
            fi

            # Backup
            sudo cp "$DOCKER_DAEMON" "$DOCKER_DAEMON.bak"

            # Extract GPU UUIDs using nvidia-smi.
            # This command extracts the UUID from lines like: "GPU UUID                             : GPU-XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
            GPU_ARRAY=$(nvidia-smi -a | grep "GPU UUID" | awk -F': ' '{print "\"NVIDIA-GPU="$2"\""}' | paste -sd, -)
            GPU_ARRAY="[$GPU_ARRAY]"

            echo "Detected GPU resources: $GPU_ARRAY"

            # Use jq to set defaults & resources with the proper GPU UUIDs
            sudo jq --argjson gpu_resources "$GPU_ARRAY" '
              .["default-runtime"] = "nvidia" |
              .runtimes.nvidia.path = "nvidia-container-runtime" |
              .runtimes.nvidia.args = [] |
              .["node-generic-resources"] = $gpu_resources
            ' "$DOCKER_DAEMON" | sudo tee "$DOCKER_DAEMON.tmp" > /dev/null

            sudo mv "$DOCKER_DAEMON.tmp" "$DOCKER_DAEMON"

            echo "Restarting Docker to apply changes..."
            sudo systemctl restart docker
            sleep 3

            if sudo systemctl is-active --quiet docker; then
                echo "Docker restarted successfully. Checking GPU resources..."
                sudo docker info | grep -A5 "Resources" || true
            else
                echo "Error: Docker failed to restart. Check logs with:"
                echo "  journalctl -u docker --no-pager | tail -n 50"
                echo "Reverting daemon.json to previous backup..."
                sudo cp "$DOCKER_DAEMON.bak" "$DOCKER_DAEMON"
                sudo systemctl restart docker
                exit 1
            fi
        else
            echo "Skipping GPU configuration."
        fi
    else
        echo "No nvidia-smi found; skipping GPU configuration."
    fi
fi

######################################
# 4.6 Create Persistent Directories
######################################
if [[ "$ARCH" == "armv7l" || "$ARCH" == "aarch64" ]]; then
    echo "This is a scribe (Raspberry Pi) node."
    echo "Creating persistent directories for transcripts..."
    sudo mkdir -p /var/lib/aiinabox/transcripts /var/lib/aiinabox/transcripts_clean
    sudo chown -R $(whoami):$(whoami) /var/lib/aiinabox/transcripts /var/lib/aiinabox/transcripts_clean
else
    echo "This is a server node."
    echo "Creating persistent directories for server data..."
    sudo mkdir -p /var/lib/aiinabox/ollamadata \
                     /var/lib/aiinabox/scraped_data/jsons \
                     /var/lib/aiinabox/scraped_data/codes \
                     /var/lib/aiinabox/scraped_data/codes_clean \
                     /var/lib/aiinabox/search_eng_data \
                     /var/lib/aiinabox/index_dir \
                     /var/lib/aiinabox/title_index_dir \
                     /var/lib/aiinabox/front_end/
    sudo chown -R $(whoami):$(whoami) /var/lib/aiinabox/ollamadata \
                     /var/lib/aiinabox/scraped_data \
                     /var/lib/aiinabox/search_eng_data \
                     /var/lib/aiinabox/index_dir \
                     /var/lib/aiinabox/title_index_dir

    # Always ask whether to pre-populate the front_end directory
    PERSISTENT_FRONTEND="/var/lib/aiinabox/front_end"
    REPO_DIR="$HOME/Documents/repos/aiinabox"
    REPO_FRONTEND="$REPO_DIR/src/front_end"

    read -p "Do you want to populate (or repopulate) the persistent front_end directory from the repository? (y/n): " populate_frontend
    if [[ "$populate_frontend" =~ ^[Yy]$ ]]; then
        echo "Populating persistent front_end directory from repository..."
        # Copy everything from the src/front_end folder first.
        sudo cp -r "$REPO_FRONTEND/"* "$PERSISTENT_FRONTEND/"

        # Next, copy additional files that your Dockerfile would have placed in /app/front_end.
        sudo cp "$REPO_DIR/src/ai_pipeline/personas/personalities.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_empty_template_p0.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_empty_template_p1.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_empty_template_p2.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_empty_template_p3.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_filled_template_p0.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_filled_template_p1.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_filled_template_p2.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/sick_visit_filled_template_p3.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/template_generator.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/data/stopwords.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/document_preprocessor.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/indexing.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/l2r.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/misc_tools.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/network_features.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/ranker.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/relevance.py" "$PERSISTENT_FRONTEND/"
    else
        echo "Skipping pre-population of persistent front_end directory."
    fi
fi

######################################
# 5. Install Host-Level Dependencies (Linux Server Only)
######################################
if [[ "$ARCH" == "armv7l" || "$ARCH" == "aarch64" ]]; then
    echo "This is a Raspberry Pi node. Skipping installation of host-level dependencies."
else
    echo "Installing host-level dependencies on Linux server..."
    # (Java, R, ChromeDriver, etc.) ...
fi

######################################
# 6. Pre-build and Launch Docker Services
######################################
DOCKER_COMPOSE_PATH="$HOME/Documents/repos/aiinabox/docker/docker-compose.yml"
REPO_DIR="$HOME/Documents/repos/aiinabox"

if [ ! -f "$DOCKER_COMPOSE_PATH" ]; then
    echo "Warning: docker-compose.yml not found at ${DOCKER_COMPOSE_PATH}."
    echo "If you wish to deploy Docker containers, please ensure the file exists."
else
    if [[ "$is_manager" =~ ^[Yy]$ ]]; then
        read -p "Do you want to pre-build and launch Docker containers now? (y/n): " launch_docker
        if [[ "$launch_docker" =~ ^[Yy]$ ]]; then
            echo "Pre-building Docker images..."
            sudo docker build -t docker-icd_10_code_scraping -f "$REPO_DIR/docker/Dockerfile_scraping" "$REPO_DIR"
            sudo docker build -t docker-icd_10_search_engine -f "$REPO_DIR/docker/Dockerfile_search_engine" "$REPO_DIR"
            sudo docker build -t docker-front_end -f "$REPO_DIR/docker/Dockerfile_front_end" "$REPO_DIR"
            sudo docker build -t docker-scribe_speech_to_text -f "$REPO_DIR/docker/Dockerfile_scribe_arm" "$REPO_DIR"
            
            echo "Deploying Docker stack 'aiinabox'..."
            sudo docker stack deploy -c "$DOCKER_COMPOSE_PATH" aiinabox

            # Wait for the overlay network and services to initialize.
            echo "Waiting for the overlay network and services to initialize..."
            sleep 15

            # Attempt to load the phi3:14b model into the Ollama container
            echo "Attempting to load the phi3:14b model into the Ollama container..."
            sleep 15
            CONTAINER_ID=$(sudo docker ps --filter "name=aiinabox_ollama" --format "{{.ID}}" | head -n 1)
            if [ -n "$CONTAINER_ID" ]; then
                echo "Pulling phi3:14b model inside the Ollama container..."
                sudo docker exec "$CONTAINER_ID" ollama run phi3:14b
            else
                echo "Error: Ollama container not found. Please check your deployment."
            fi
        else
            echo "Skipping Docker container deployment. You can launch them later with:"
            echo "  docker stack deploy -c $DOCKER_COMPOSE_PATH aiinabox"
        fi
    else
        echo "This is not the swarm manager node. Docker stack deployment must be performed on a manager node."
    fi
fi

######################################
# 7. Final Messages
######################################
echo "Installation complete."
if [[ "$ARCH" != "armv7l" && "$ARCH" != "aarch64" ]]; then
    echo "Host-level dependencies installed on Linux server, plus optional GPU config if you chose it."
else
    echo "Scribe-specific directories created for transcripts."
fi
if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    echo "Docker services deployed. Check the status with:"
    echo "  sudo docker stack ps aiinabox"
else
    echo "Docker services were not deployed from this node. Please deploy them from the swarm manager node when ready."
fi
