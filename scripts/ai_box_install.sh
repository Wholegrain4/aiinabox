#!/bin/bash
# install_aiinabox.sh
# Unified installation script for AI in a Box
# - Sets up Docker (and Docker Swarm)
# - Optionally sets up Mosquitto MQTT broker for inter-machine communication
# - Sets up optional local registry
# - Configures GPU (if present)
# - Builds & deploys Docker stack if desired

set -e

# ------------------------------------------------
# 1. Default Settings & Global Variables
# ------------------------------------------------

DEFAULT_REGISTRY_IP="192.168.40.187"
REGISTRY_PORT="5001"
REGISTRY="${DEFAULT_REGISTRY_IP}:${REGISTRY_PORT}"

MQTT_PORT="1883"  # Port for Mosquitto broker

# Path to your AI-in-a-Box repository (server side)
REPO_DIR="/home/trace-grain/Documents/repos/aiinabox"
DOCKER_COMPOSE_PATH="$REPO_DIR/docker/docker-compose.yml"

echo "=== AI in a Box: Server Installation Script ==="

# ------------------------------------------------
# 2. Helper Functions
# ------------------------------------------------

function ensure_docker_running() {
    if ! sudo systemctl is-active --quiet docker; then
        echo "Docker daemon not running. Attempting to start Docker..."
        sudo systemctl start docker
        sleep 3
    fi
    if ! sudo systemctl is-active --quiet docker; then
        echo "ERROR: Docker service is not running. Check 'sudo systemctl status docker'."
        exit 1
    fi
}

function setup_qemu_emulation() {
    # Only relevant on x86_64 for multi-arch builds
    if [ "$(uname -m)" != "x86_64" ]; then
        echo "Not an x86_64 system. Skipping QEMU multi-arch setup."
        return
    fi
    echo "Installing qemu-user-static for multi-arch builds..."
    sudo apt-get update && sudo apt-get install -y qemu-user-static
    echo "Registering QEMU emulation with Docker Buildx..."
    sudo docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
}

function configure_insecure_registry() {
    local registry_addr="$1"
    local DOCKER_DAEMON="/etc/docker/daemon.json"

    echo "Configuring Docker daemon for insecure registry: '${registry_addr}'..."

    # Ensure jq is available
    if ! command -v jq &> /dev/null; then
        sudo apt-get update && sudo apt-get install -y jq
    fi

    # Create daemon.json if it doesn't exist
    if [ ! -f "$DOCKER_DAEMON" ]; then
        echo "{}" | sudo tee "$DOCKER_DAEMON" > /dev/null
    fi

    sudo cp "$DOCKER_DAEMON" "$DOCKER_DAEMON.bak"

    # Add registry to "insecure-registries"
    sudo jq --arg reg "$registry_addr" '
      .["insecure-registries"] += [$reg]
    ' "$DOCKER_DAEMON" | sudo tee "$DOCKER_DAEMON.tmp" > /dev/null

    sudo mv "$DOCKER_DAEMON.tmp" "$DOCKER_DAEMON"
    echo "Restarting Docker to apply the insecure registry setting..."
    sudo systemctl restart docker
    sleep 3
    if ! sudo systemctl is-active --quiet docker; then
        echo "ERROR: Docker failed to restart. Reverting changes..."
        sudo cp "$DOCKER_DAEMON.bak" "$DOCKER_DAEMON"
        sudo systemctl restart docker
        exit 1
    fi
    echo "Insecure registry '${registry_addr}' configured successfully."
}

function ensure_local_registry() {
    local registry_name="registry"
    if sudo docker ps -a --format '{{.Names}}' | grep -q "^${registry_name}$"; then
        # If container exists, ensure correct port or remove it
        current_mapping=$(sudo docker inspect "${registry_name}" | \
            jq -r '.[0].NetworkSettings.Ports["5000/tcp"][0].HostPort' 2>/dev/null || true)
        if [ "$current_mapping" != "$REGISTRY_PORT" ]; then
            echo "Found registry container but mapped to port ${current_mapping}, removing..."
            sudo docker rm -f "${registry_name}"
        else
            # If it's already running, do nothing
            if sudo docker ps --format '{{.Names}}' | grep -q "^${registry_name}$"; then
                echo "Local Docker registry '${registry_name}' is already running."
                return
            fi
        fi
    fi

    # Ask user if we should create a new local registry
    read -p "Create a local Docker registry on port ${REGISTRY_PORT}? (y/n): " create_reg
    if [[ "$create_reg" =~ ^[Yy]$ ]]; then
        echo "Creating local registry container on port ${REGISTRY_PORT}..."
        sudo docker run -d \
            -p 0.0.0.0:${REGISTRY_PORT}:5000 \
            --restart=always \
            --name "${registry_name}" \
            registry:2
        echo "Local registry container '${registry_name}' started."
    else
        echo "Skipping local registry creation."
    fi
}

function open_firewall_port() {
    # Tries both UFW and firewalld as relevant
    local port="$1"
    read -p "Open port ${port}/tcp in the firewall? (y/n): " fw_open
    if [[ "$fw_open" =~ ^[Yy]$ ]]; then
        if command -v ufw &> /dev/null && sudo ufw status | grep -q "Status: active"; then
            echo "Allowing ${port}/tcp via UFW..."
            sudo ufw allow ${port}/tcp || true
        elif command -v firewall-cmd &> /dev/null; then
            echo "Allowing ${port}/tcp via firewalld..."
            sudo firewall-cmd --permanent --add-port=${port}/tcp || true
            sudo firewall-cmd --reload || true
        else
            echo "No supported firewall detected; please open port ${port} manually if needed."
        fi
    else
        echo "Skipping firewall configuration for port ${port}."
    fi
}

function setup_mqtt_broker() {
    echo "=== Setting up Mosquitto MQTT broker ==="
    sudo apt update && sudo apt install -y mosquitto mosquitto-clients

    # Configure the broker to listen on 0.0.0.0:1883, disallow anonymous
    cat <<EOF | sudo tee /etc/mosquitto/conf.d/listener.conf
listener ${MQTT_PORT} 0.0.0.0
allow_anonymous false
password_file /etc/mosquitto/passwd
EOF

    # Create default user 'mqttuser' (prompt could be customized)
    echo "Creating a Mosquitto user 'mqttuser' (please enter a password)..."
    sudo mosquitto_passwd -c /etc/mosquitto/passwd mqttuser

    # Change ownership of the password file so Mosquitto can read it
    sudo chown mosquitto:mosquitto /etc/mosquitto/passwd

    sudo systemctl enable --now mosquitto

    # Open firewall port 1883
    if command -v ufw &>/dev/null && sudo ufw status | grep -q "Status: active"; then
        echo "Allowing 1883/tcp in UFW..."
        sudo ufw allow 1883/tcp || true
    fi
    if command -v firewall-cmd &>/dev/null; then
        echo "Allowing 1883/tcp in firewalld..."
        sudo firewall-cmd --permanent --add-port=1883/tcp || true
        sudo firewall-cmd --reload || true
    fi

    echo "Mosquitto installed and configured. Broker listening on port ${MQTT_PORT}."
    echo "Use the 'mqttuser' credentials you just created to connect."
}

# ------------------------------------------------
# 3. Main Script Execution
# ------------------------------------------------

# -- Docker check/install --
echo "Checking for Docker..."
if ! command -v docker &>/dev/null; then
    echo "Docker not found. Installing..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. You may need to log out/in for group changes to take effect."
else
    echo "Docker is already installed."
fi
ensure_docker_running

# -- Docker Compose plugin check --
echo "Checking for Docker Compose plugin..."
if ! docker compose version &>/dev/null; then
    echo "Docker Compose plugin not found. Installing..."
    sudo apt-get update && sudo apt-get install -y docker-compose-plugin
else
    echo "Docker Compose plugin is installed."
fi

# -- QEMU multi-arch setup (only relevant on x86_64) --
setup_qemu_emulation

# -- Swarm initialization or join --
read -p "Is this the Swarm manager node? (y/n): " is_manager
if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    echo "Setting up this node as the Swarm manager..."
    if ! sudo docker info 2>/dev/null | grep -q "Swarm: active"; then
        MGR_IP=$(hostname -I | awk '{print $1}')
        echo "Initializing Docker Swarm with advertise-addr=${MGR_IP}..."
        sudo docker swarm init --advertise-addr "${MGR_IP}"
    else
        echo "Swarm is already active on this node."
    fi

    # Ask user if they'd like to set up MQTT on the manager
    read -p "Install Mosquitto MQTT broker on this server? (y/n): " install_mqtt
    if [[ "$install_mqtt" =~ ^[Yy]$ ]]; then
        setup_mqtt_broker
    else
        echo "Skipping MQTT broker setup."
    fi

    # Local registry
    ensure_local_registry
    open_firewall_port "${REGISTRY_PORT}"
else
    echo "Joining this node to an existing Swarm as a worker..."
    read -p "Manager node IP: " manager_ip
    read -p "Swarm join token: " join_token
    sudo docker swarm join --token "${join_token}" "${manager_ip}:2377"

    # Worker might also need insecure registry config
    read -p "Use registry '${REGISTRY}' as insecure on this worker? (y/n): " worker_reg
    if [[ "$worker_reg" =~ ^[Yy]$ ]]; then
        configure_insecure_registry "${REGISTRY}"
    fi
fi

# -- Node labeling (always 'server' for this script) --
NODE_ID=$(sudo docker info -f '{{.Swarm.NodeID}}')
echo "Labeling this node 'hardware=server'..."
sudo docker node update --label-add hardware=server "${NODE_ID}"

# -- Optionally configure NVIDIA GPU for Docker Swarm --
if command -v nvidia-smi &>/dev/null; then
    echo "NVIDIA GPU detected on this system."
    read -p "Configure GPU for Docker Swarm? (y/n): " setup_gpu
    if [[ "$setup_gpu" =~ ^[Yy]$ ]]; then
        local_daemon="/etc/docker/daemon.json"
        if ! command -v jq &>/dev/null; then
            sudo apt-get update && sudo apt-get install -y jq
        fi
        [ ! -f "$local_daemon" ] && echo "{}" | sudo tee "$local_daemon" >/dev/null
        sudo cp "$local_daemon" "$local_daemon.bak"

        GPU_ARRAY=$(nvidia-smi -a | grep "GPU UUID" | awk -F': ' '{print "\"NVIDIA-GPU="$2"\""}' | paste -sd, -)
        GPU_ARRAY="[$GPU_ARRAY]"

        echo "Detected GPU resources: $GPU_ARRAY"
        sudo jq --argjson gpu_resources "$GPU_ARRAY" '
            .["default-runtime"] = "nvidia" |
            .runtimes.nvidia.path = "nvidia-container-runtime" |
            .runtimes.nvidia.args = [] |
            .["node-generic-resources"] = $gpu_resources
        ' "$local_daemon" | sudo tee "$local_daemon.tmp" >/dev/null

        sudo mv "$local_daemon.tmp" "$local_daemon"
        echo "Restarting Docker to apply GPU config..."
        sudo systemctl restart docker
        sleep 3
        if ! sudo systemctl is-active --quiet docker; then
            echo "ERROR: Docker failed to restart. Reverting..."
            sudo cp "$local_daemon.bak" "$local_daemon"
            sudo systemctl restart docker
            exit 1
        fi
        echo "GPU configuration applied successfully."
    fi
fi

# -- Create persistent directories on the server --
echo "Creating persistent directories in /var/lib/aiinabox..."
sudo mkdir -p \
  /var/lib/aiinabox/ollamadata \
  /var/lib/aiinabox/scraped_data/jsons \
  /var/lib/aiinabox/scraped_data/codes \
  /var/lib/aiinabox/scraped_data/codes_clean \
  /var/lib/aiinabox/search_eng_data \
  /var/lib/aiinabox/index_dir \
  /var/lib/aiinabox/title_index_dir \
  /var/lib/aiinabox/front_end

sudo chown -R "$(whoami)":"$(whoami)" /var/lib/aiinabox

# -- (Optional) Prepopulate front_end from repo --
PERSISTENT_FRONTEND="/var/lib/aiinabox/front_end"
REPO_FRONTEND="$REPO_DIR/src/front_end"

read -p "Populate /var/lib/aiinabox/front_end from the repo? (y/n): " populate_frontend
if [[ "$populate_frontend" =~ ^[Yy]$ ]]; then
    echo "Copying front_end files from $REPO_FRONTEND -> $PERSISTENT_FRONTEND..."
    sudo cp -r "$REPO_FRONTEND/"* "$PERSISTENT_FRONTEND/"
    # Additional template or pipeline files if needed:
    sudo cp "$REPO_DIR/src/ai_pipeline/personas/personalities.py" "$PERSISTENT_FRONTEND/" || true
    sudo cp "$REPO_DIR/src/ai_pipeline/template_generator.py" "$PERSISTENT_FRONTEND/" || true
    sudo cp "$REPO_DIR/src/ai_pipeline/templates/"sick_visit_*_template_p{0,1,2,3}.txt "$PERSISTENT_FRONTEND/" || true
    sudo cp "$REPO_DIR/src/search_engine/data/stopwords.txt" "$PERSISTENT_FRONTEND/" || true
    sudo cp "$REPO_DIR/src/search_engine/"{document_preprocessor.py,indexing.py,l2r.py,misc_tools.py,network_features.py,ranker.py,relevance.py} \
       "$PERSISTENT_FRONTEND/" || true
else
    echo "Skipping front_end directory population."
fi

# -- Deploy Docker stack (manager only) if user wants to build images now --
if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    if [ ! -f "$DOCKER_COMPOSE_PATH" ]; then
        echo "WARNING: $DOCKER_COMPOSE_PATH not found. Cannot deploy stack."
        exit 0
    fi

    read -p "Do you want to build/push images and deploy the Docker stack now? (y/n): " launch_stack
    if [[ "$launch_stack" =~ ^[Yy]$ ]]; then

        # Create /etc/buildkit.toml to allow pushing to insecure registry
        echo "Configuring /etc/buildkit.toml for insecure registry at http://${REGISTRY}..."
        cat <<EOF | sudo tee /etc/buildkit.toml
debug = false

[registry."${REGISTRY}"]
  http = true
  insecure = true
EOF

        # Remove old builder if it exists
        if docker buildx ls | grep -q "multiarch-builder"; then
            echo "Removing existing 'multiarch-builder' buildx instance..."
            docker buildx rm multiarch-builder || true
        fi

        # Create new buildx builder with custom config
        echo "Creating buildx builder 'multiarch-builder'..."
        docker buildx create \
          --driver docker-container \
          --config /etc/buildkit.toml \
          --name multiarch-builder \
          --use
        docker buildx inspect --bootstrap

        echo "Building multi-arch images and pushing to ${REGISTRY}..."

        # Example: ICD-10 code scraping
        docker buildx build \
          --platform linux/amd64 \
          -t ${REGISTRY}/docker-icd_10_code_scraping:latest \
          -f "$REPO_DIR/docker/Dockerfile_scraping" \
          "$REPO_DIR" \
          --push

        # Example: ICD-10 search engine
        docker buildx build \
          --platform linux/amd64 \
          -t ${REGISTRY}/docker-icd_10_search_engine:latest \
          -f "$REPO_DIR/docker/Dockerfile_search_engine" \
          "$REPO_DIR" \
          --push

        # Example: front_end
        docker buildx build \
          --platform linux/amd64 \
          -t ${REGISTRY}/docker-front_end:latest \
          -f "$REPO_DIR/docker/Dockerfile_front_end" \
          "$REPO_DIR" \
          --push

        # ---------------------------------------------------------------
        # BUILD SCRIBE_CONSUMER HERE
        # ---------------------------------------------------------------
        docker buildx build \
          --platform linux/amd64 \
          -t ${REGISTRY}/docker-scribe_consumer:latest \
          -f "$REPO_DIR/scribe_consumer/Dockerfile" \
          "$REPO_DIR/scribe_consumer" \
          --push

        # If you have a custom Ollama Dockerfile or other services, build them here as well.

        echo "Deploying stack 'aiinabox' with $DOCKER_COMPOSE_PATH..."
        sudo docker stack deploy -c "$DOCKER_COMPOSE_PATH" aiinabox

        echo "Waiting for services to initialize..."
        sleep 15

        # Optionally load a model into Ollama container
        read -p "Attempt to load phi3:14b model in Ollama container? (y/n): " load_model
        if [[ "$load_model" =~ ^[Yy]$ ]]; then
            CONTAINER_ID=$(sudo docker ps --filter "name=aiinabox_ollama" --format "{{.ID}}" | head -n 1)
            if [ -n "$CONTAINER_ID" ]; then
                echo "Pulling phi3:14b model inside the Ollama container..."
                sudo docker exec "$CONTAINER_ID" ollama run phi3:14b
            else
                echo "Error: Ollama container not found. Check your services."
            fi
        fi
    else
        echo "Skipping build and deploy. You can do so later with:"
        echo "  docker compose build"
        echo "  docker compose push"
        echo "  docker stack deploy -c $DOCKER_COMPOSE_PATH aiinabox"
    fi
else
    echo "Worker node: stack deploy must be done on the manager."
fi

echo "=== Installation complete. ==="
echo "Check 'docker node ls' and 'docker stack ps aiinabox' (manager) to confirm status."
