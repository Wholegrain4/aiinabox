#!/bin/bash
# install_aiinabox.sh
# Unified installation script for AI in a Box.
#
# This script:
#   - Installs Docker and the Docker Compose plugin.
#   - Sets up (or joins) a Docker Swarm with node labeling based on hardware (Raspberry Pi vs. Linux server).
#   - Installs host-level dependencies (Java, R, Selenium working directory, ChromeDriver) only on the Linux server.
#   - Optionally builds & launches your Docker containers (only from the swarm manager node).
#
# IT professionals can adjust and test the software natively if desired.
#
# Usage: ./install_aiinabox.sh
# Note: Some parts require sudo privileges.

set -e

echo "=== AI in a Box Unified Installation ==="

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
    if ! docker info | grep -q "Swarm: active"; then
        docker swarm init
    else
        echo "Swarm is already active on this node."
    fi
else
    echo "This node will join an existing swarm as a worker."
    read -p "Enter the manager node IP: " manager_ip
    read -p "Enter the swarm join token: " join_token
    docker swarm join --token "$join_token" "$manager_ip:2377"
fi

######################################
# 4. Label Node Based on Hardware Architecture
######################################
NODE_ID=$(docker info -f '{{.Swarm.NodeID}}')
ARCH=$(uname -m)
if [[ "$ARCH" == "armv7l" || "$ARCH" == "aarch64" ]]; then
    echo "Detected Raspberry Pi architecture ($ARCH). Labeling node as hardware=raspberrypi."
    docker node update --label-add hardware=raspberrypi "$NODE_ID"
else
    echo "Detected architecture ($ARCH) (assumed Linux server). Labeling node as hardware=server."
    docker node update --label-add hardware=server "$NODE_ID"
fi

######################################
# 5. Install Host-Level Dependencies (Linux Server Only)
######################################
if [[ "$ARCH" == "armv7l" || "$ARCH" == "aarch64" ]]; then
    echo "This is a Raspberry Pi node. Skipping installation of host-level dependencies."
else
    echo "Installing host-level dependencies on Linux server..."

    # 5.1 Check and Install Java
    echo "Checking for Java..."
    if ! command -v java &> /dev/null; then
        echo "Java not found. Installing Java..."
        sudo apt-get update
        sudo apt-get install -y default-jre
    else
        echo "Java is already installed."
    fi

    # 5.2 Check and Install R
    echo "Checking for R..."
    if ! command -v R &> /dev/null; then
        echo "R not found. Installing R..."
        sudo apt-get update
        sudo apt-get install -y r-base
    else
        echo "R is already installed."
    fi

    # 5.3 Create Selenium Working Directory
    echo "Ensuring Selenium working directory is created..."
    Rscript -e "if (!requireNamespace('wdman', quietly = TRUE)) { install.packages('wdman', repos='https://cloud.r-project.org') }"
    Rscript -e "if (!dir.exists('~/.local/')) { wdman::selenium() } else { message('~/.local already exists') }"

    # 5.4 Copy and Install ChromeDriver
    echo "Installing ChromeDriver..."
    REPO_DIR="$HOME/Documents/repos/aiinabox"
    CHROMEDRIVER_DIR="${REPO_DIR}/bin/133.0.6943.53"
    CHROMEDRIVER_SRC="${CHROMEDRIVER_DIR}/chromedriver"

    if [ ! -f "$CHROMEDRIVER_SRC" ]; then
        echo "Error: ChromeDriver not found at ${CHROMEDRIVER_SRC}"
        exit 1
    fi

    CHROMEDRIVER_LOCAL_BIN="$HOME/.local/share/binman_chromedriver/linux64"
    mkdir -p "$CHROMEDRIVER_LOCAL_BIN"
    echo "Copying ChromeDriver from repository to ${CHROMEDRIVER_LOCAL_BIN}..."
    cp -r "$CHROMEDRIVER_DIR" "$CHROMEDRIVER_LOCAL_BIN"

    TARGET_DRIVER="${CHROMEDRIVER_LOCAL_BIN}/133.0.6943.53/chromedriver"
    if [ ! -f "$TARGET_DRIVER" ]; then
        echo "Error: ChromeDriver not found at ${TARGET_DRIVER}"
        exit 1
    fi
    chmod +x "$TARGET_DRIVER"
    echo "ChromeDriver installed at ${TARGET_DRIVER}"

    # 5.5 Check and Install legacy docker-compose (if needed)
    echo "Checking for legacy docker-compose..."
    if ! command -v docker-compose &> /dev/null; then
        echo "docker-compose not found. Installing legacy docker-compose..."
        sudo apt-get update
        sudo apt-get install -y docker-compose
    else
        echo "docker-compose is installed."
    fi

    # 5.6 Extract and Install Chrome from tar.xz (contains google-chrome-stable_current_amd64.deb)
    CHROME_ARCHIVE="${REPO_DIR}/bin/Chrome.tar.xz"
    if [ -f "$CHROME_ARCHIVE" ]; then
        echo "Extracting Chrome from $CHROME_ARCHIVE..."
        # Extract to /tmp directory
        tar -xf "$CHROME_ARCHIVE" -C /tmp
        # Expect the extracted file to be named google-chrome-stable_current_amd64.deb
        DEB_FILE="/tmp/google-chrome-stable_current_amd64.deb"
        if [ -f "$DEB_FILE" ]; then
            echo "Installing Chrome from $DEB_FILE..."
            sudo dpkg -i "$DEB_FILE" || sudo apt-get -f install -y
            echo "Chrome installed."
            # (Optional) Clean up the .deb file
            rm "$DEB_FILE"
        else
            echo "Error: $DEB_FILE not found after extraction."
        fi
    else
        echo "Warning: $CHROME_ARCHIVE not found; skipping Chrome installation."
    fi
fi

######################################
# 6. Build and (Optionally) Launch Docker Services
######################################
# Define the path to your unified docker-compose.yml file.
DOCKER_COMPOSE_PATH="$HOME/Documents/repos/aiinabox/docker/docker-compose.yml"

if [ ! -f "$DOCKER_COMPOSE_PATH" ]; then
    echo "Warning: docker-compose.yml not found at ${DOCKER_COMPOSE_PATH}."
    echo "If you wish to deploy Docker containers, please ensure the file exists."
else
    if [[ "$is_manager" =~ ^[Yy]$ ]]; then
        read -p "Do you want to build and launch Docker containers now? (y/n): " launch_docker
        if [[ "$launch_docker" =~ ^[Yy]$ ]]; then
            echo "Building Docker images..."
            docker compose -f "$DOCKER_COMPOSE_PATH" build
            echo "Deploying Docker stack 'aiinabox'..."
            docker stack deploy -c "$DOCKER_COMPOSE_PATH" aiinabox
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
    echo "Host-level dependencies installed on Linux server:"
    echo "  - Java"
    echo "  - R"
    echo "  - Selenium working directory created"
    echo "  - ChromeDriver installed at ${TARGET_DRIVER}"
    echo "  - Chrome installed from tar.xz (if present)"
fi
if [[ "$is_manager" =~ ^[Yy]$ ]]; then
    echo "Docker services deployed (if chosen). Check the status with:"
    echo "  docker stack ps aiinabox"
else
    echo "Docker services were not deployed from this node. Please deploy them from the swarm manager node when ready."
fi
