#!/bin/bash
# install_aiinabox.sh
# Unified installation script for AI in a Box (manager or worker)
# Now with private registry integration and prompts to create/use it as insecure.

set -e

# Default registry address/port (adjust as needed)
DEFAULT_REGISTRY_IP="192.168.40.187"
REGISTRY_PORT="5001"
REGISTRY="${DEFAULT_REGISTRY_IP}:${REGISTRY_PORT}"

echo "=== AI in a Box Unified Installation ==="

######################################
# 0. Functions
######################################

function ensure_docker_running() {
    if ! sudo systemctl is-active --quiet docker; then
        echo "Docker daemon is not running. Attempting to start Docker..."
        sudo systemctl start docker
        sleep 3
    fi

    if ! sudo systemctl is-active --quiet docker; then
        echo "ERROR: Docker service is not running, and we cannot start it."
        echo "Check 'sudo systemctl status docker' for more info."
        exit 1
    fi
}

# Prompt to configure /etc/docker/daemon.json with insecure registry entry
function configure_insecure_registry() {
    local registry_addr="$1"
    local DOCKER_DAEMON="/etc/docker/daemon.json"

    if grep -q "\"insecure-registries\"" "$DOCKER_DAEMON" 2>/dev/null; then
        if grep -q "${registry_addr}" "$DOCKER_DAEMON"; then
            echo "Insecure registry '${registry_addr}' is already configured in $DOCKER_DAEMON"
            return
        fi
    fi

    echo "Configuring insecure registry '${registry_addr}' in $DOCKER_DAEMON..."
    
    if ! command -v jq &> /dev/null; then
        echo "Installing jq for JSON editing..."
        sudo apt-get update
        sudo apt-get install -y jq
    fi

    if [ ! -f "$DOCKER_DAEMON" ]; then
        echo "{}" | sudo tee "$DOCKER_DAEMON" > /dev/null
    fi

    sudo cp "$DOCKER_DAEMON" "$DOCKER_DAEMON.bak"

    sudo jq --arg reg "$registry_addr" '
      .["insecure-registries"] += [$reg]
    ' "$DOCKER_DAEMON" | sudo tee "$DOCKER_DAEMON.tmp" > /dev/null

    sudo mv "$DOCKER_DAEMON.tmp" "$DOCKER_DAEMON"

    echo "Restarting Docker to apply insecure registry settings..."
    sudo systemctl restart docker
    sleep 3

    if sudo systemctl is-active --quiet docker; then
        echo "Docker restarted successfully. Insecure registry config applied."
    else
        echo "Error: Docker failed to restart after registry config. Reverting changes..."
        sudo cp "$DOCKER_DAEMON.bak" "$DOCKER_DAEMON"
        sudo systemctl restart docker
        exit 1
    fi
}

# Prompt to create local private registry container if not running
function ensure_local_registry() {
    local registry_name="registry"
    local registry_port="$REGISTRY_PORT"

    if sudo docker ps --format '{{.Names}}' | grep -q "^${registry_name}$"; then
        echo "Local Docker registry container '${registry_name}' is already running."
        return
    fi

    echo
    echo "No local registry container detected."
    read -p "Do you want to create a local Docker registry container (port ${registry_port})? (y/n): " create_reg
    if [[ "$create_reg" =~ ^[Yy]$ ]]; then
        echo "Creating local registry on port ${registry_port}..."
        # Bind explicitly to all interfaces using 0.0.0.0
        sudo docker run -d -p 0.0.0.0:${registry_port}:5000 --restart=always --name ${registry_name} registry:2
        echo "Local registry '${registry_name}' started."
    else
        echo "Skipping local registry creation."
    fi
}

######################################
# 1. Check Docker / Docker Compose
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

ensure_docker_running

echo "Checking for Docker Compose plugin..."
if ! docker compose version &> /dev/null; then
    echo "Docker Compose plugin not found. Installing..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
else
    echo "Docker Compose plugin is installed."
fi

######################################
# 2. Swarm Setup: Manager or Worker?
######################################
read -p "Is this the swarm manager node? (y/n): " is_manager
if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    echo "This node will act as the swarm manager."
    if ! sudo docker info 2>/dev/null | grep -q "Swarm: active"; then
        IP=$(hostname -I | awk '{print $1}')
        echo "Initializing Docker Swarm with advertise address: $IP"
        sudo docker swarm init --advertise-addr "$IP"
    else
        echo "Swarm is already active on this node."
    fi

    # Prompt to create local registry on manager
    ensure_local_registry
else
    echo "This node will join an existing swarm as a worker."
    read -p "Enter the manager node IP: " manager_ip
    read -p "Enter the swarm join token: " join_token
    sudo docker swarm join --token "$join_token" "$manager_ip:2377"

    read -p "Does this worker need to pull images from an insecure registry at ${REGISTRY}? (y/n): " worker_insecure
    if [[ "$worker_insecure" =~ ^[Yy]$ ]]; then
        configure_insecure_registry "${REGISTRY}"
    fi
fi

######################################
# 3. Architecture Detection and Labeling
######################################
ARCH=$(uname -m)
NODE_ID=$(sudo docker info -f '{{.Swarm.NodeID}}')

REPO_DIR_SERVER="/home/trace-grain/Documents/repos/aiinabox"
REPO_DIR_SCRIBE="/home/wholegrain4/Documents/repos/aiinabox"

if [[ "$ARCH" == "armv7l" || "$ARCH" == "aarch64" ]]; then
    echo "Detected Raspberry Pi architecture ($ARCH)."
    if [[ "$is_manager" =~ ^[Yy]$ ]]; then
        echo "Labeling node as hardware=raspberrypi locally on this manager node."
        sudo docker node update --label-add hardware=raspberrypi "$NODE_ID"
    else
        echo "Worker node (Pi). Label must be updated from the manager."
        if [ -z "$manager_ip" ]; then
            read -p "Enter the manager node IP: " manager_ip
        fi
        read -p "Enter manager node SSH username for labeling: " MANAGER_SSH_USER
        echo "Updating node label on manager node..."
        ssh "$MANAGER_SSH_USER@$manager_ip" "docker node update --label-add hardware=raspberrypi $NODE_ID"
    fi
    IS_SCRIBE=true
    REPO_DIR="$REPO_DIR_SCRIBE"
else
    echo "Detected architecture ($ARCH). Labeling node as hardware=server."
    sudo docker node update --label-add hardware=server "$NODE_ID"
    IS_SCRIBE=false
    REPO_DIR="$REPO_DIR_SERVER"
fi

######################################
# 3.5 Insecure Registry Config (all nodes)
######################################
read -p "Do you want to configure this node to use the registry at ${REGISTRY} as insecure? (y/n): " config_insecure
if [[ "$config_insecure" =~ ^[Yy]$ ]]; then
    configure_insecure_registry "${REGISTRY}"
fi

######################################
# 4. GPU Setup (only on Linux server)
######################################
if [[ "$IS_SCRIBE" == false ]]; then
    if command -v nvidia-smi &> /dev/null; then
        echo "NVIDIA GPU detected."
        read -p "Do you want to configure the GPU for Docker Swarm? (y/n): " setup_gpu
        if [[ "$setup_gpu" =~ ^[Yy]$ ]]; then
            DOCKER_DAEMON="/etc/docker/daemon.json"
            echo "Configuring node-generic-resources for NVIDIA GPU in $DOCKER_DAEMON..."

            if ! command -v jq &> /dev/null; then
                echo "Installing jq..."
                sudo apt-get update
                sudo apt-get install -y jq
            fi

            if [ ! -f "$DOCKER_DAEMON" ]; then
                echo "{}" | sudo tee "$DOCKER_DAEMON" > /dev/null
            fi

            sudo cp "$DOCKER_DAEMON" "$DOCKER_DAEMON.bak"

            GPU_ARRAY=$(nvidia-smi -a | grep "GPU UUID" | awk -F': ' '{print "\"NVIDIA-GPU="$2"\""}' | paste -sd, -)
            GPU_ARRAY="[$GPU_ARRAY]"

            echo "Detected GPU resources: $GPU_ARRAY"

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
                echo "Error: Docker failed to restart. Reverting changes..."
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
# 5. Create Directories
######################################
if [[ "$IS_SCRIBE" == true ]]; then
    echo "Creating persistent directories for transcripts (scribe)..."
    sudo mkdir -p /var/lib/aiinabox/transcripts /var/lib/aiinabox/transcripts_clean
    sudo chown -R $(whoami):$(whoami) /var/lib/aiinabox/transcripts /var/lib/aiinabox/transcripts_clean
else
    echo "Creating persistent directories for the server node..."
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

    PERSISTENT_FRONTEND="/var/lib/aiinabox/front_end"
    REPO_FRONTEND="$REPO_DIR/src/front_end"

    read -p "Do you want to populate (or repopulate) the persistent front_end directory from the repository? (y/n): " populate_frontend
    if [[ "$populate_frontend" =~ ^[Yy]$ ]]; then
        echo "Populating persistent front_end directory from repository..."
        sudo cp -r "$REPO_FRONTEND/"* "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/personas/personalities.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/templates/"sick_visit_*_template_p{0,1,2,3}.txt "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/ai_pipeline/template_generator.py" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/data/stopwords.txt" "$PERSISTENT_FRONTEND/"
        sudo cp "$REPO_DIR/src/search_engine/"{document_preprocessor.py,indexing.py,l2r.py,misc_tools.py,network_features.py,ranker.py,relevance.py} "$PERSISTENT_FRONTEND/"
    else
        echo "Skipping pre-population of persistent front_end directory."
    fi
fi

######################################
# 6. Install Host-Level Dependencies (Server Only)
######################################
if [[ "$IS_SCRIBE" == true ]]; then
    echo "Scribe node: skipping host-level dependencies."
else
    echo "Installing host-level dependencies on Linux server..."
    # e.g., apt-get install -y default-jre or R, etc.
fi

######################################
# 7. Build/Push Images & Deploy Docker Stack
######################################
DOCKER_COMPOSE_PATH="$REPO_DIR/docker/docker-compose.yml"

if [ ! -f "$DOCKER_COMPOSE_PATH" ]; then
    echo "Warning: docker-compose.yml not found at $DOCKER_COMPOSE_PATH."
    echo "Please ensure the file exists before deploying."
else
    if [[ "$is_manager" =~ ^[Yy]$ ]]; then
        read -p "Do you want to pre-build and launch Docker containers now? (y/n): " launch_docker
        if [[ "$launch_docker" =~ ^[Yy]$ ]]; then
            echo "Pre-building Docker images..."

            if [[ "$IS_SCRIBE" == true ]]; then
                echo "Detected Raspberry Pi manager. Building scribe image locally..."
                sudo docker build -t docker-scribe_speech_to_text -f "$REPO_DIR/docker/Dockerfile_scribe_arm" "$REPO_DIR"
                echo "Tagging scribe image for private registry..."
                sudo docker tag docker-scribe_speech_to_text:latest ${REGISTRY}/docker-scribe_speech_to_text:latest
                echo "Pushing scribe image to private registry..."
                sudo docker push ${REGISTRY}/docker-scribe_speech_to_text:latest
            else
                echo "Detected server manager. Building server-related images..."
                sudo docker build -t docker-icd_10_code_scraping -f "$REPO_DIR/docker/Dockerfile_scraping" "$REPO_DIR"
                sudo docker build -t docker-icd_10_search_engine -f "$REPO_DIR/docker/Dockerfile_search_engine" "$REPO_DIR"
                sudo docker build -t docker-front_end -f "$REPO_DIR/docker/Dockerfile_front_end" "$REPO_DIR"
                sudo docker build -t docker-scribe_speech_to_text -f "$REPO_DIR/docker/Dockerfile_scribe_arm" "$REPO_DIR"
                
                echo "Tagging and pushing images to private registry..."
                sudo docker tag docker-icd_10_code_scraping:latest ${REGISTRY}/docker-icd_10_code_scraping:latest
                sudo docker push ${REGISTRY}/docker-icd_10_code_scraping:latest

                sudo docker tag docker-icd_10_search_engine:latest ${REGISTRY}/docker-icd_10_search_engine:latest
                sudo docker push ${REGISTRY}/docker-icd_10_search_engine:latest

                sudo docker tag docker-front_end:latest ${REGISTRY}/docker-front_end:latest
                sudo docker push ${REGISTRY}/docker-front_end:latest

                sudo docker tag docker-scribe_speech_to_text:latest ${REGISTRY}/docker-scribe_speech_to_text:latest
                sudo docker push ${REGISTRY}/docker-scribe_speech_to_text:latest
            fi

            echo "Deploying Docker stack 'aiinabox'..."
            sudo docker stack deploy -c "$DOCKER_COMPOSE_PATH" aiinabox

            echo "Waiting for the overlay network and services to initialize..."
            sleep 15

            if [[ "$IS_SCRIBE" == false ]]; then
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
                echo "Scribe node has no Ollama container. Skipping model pull."
            fi
        else
            echo "Skipping Docker deployment. You can run later with:"
            echo "  sudo docker stack deploy -c $DOCKER_COMPOSE_PATH aiinabox"
        fi
    else
        echo "Worker node: Docker stack deployment must be done on the manager."
    fi
fi

######################################
# 8. Final Messages
######################################
echo "Installation complete."
if [[ "$IS_SCRIBE" == true ]]; then
    echo "Scribe node: transcript directories created."
else
    echo "Server node: host-level dependencies installed (if any) and optional GPU config done."
fi

if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    echo "Stack deployed (if chosen). Check status with:"
    echo "  sudo docker stack ps aiinabox"
else
    echo "Worker node: no stack deployed from here."
fi
