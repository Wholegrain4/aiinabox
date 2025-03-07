#!/bin/bash
set -e  # exit on any error

# --------------------------------------------------------
# 1) MQTT Environment Variables
# --------------------------------------------------------
export MQTT_BROKER_HOST="192.168.40.187"
export MQTT_BROKER_PORT="1883"
export MQTT_USER="mqttuser"
export MQTT_PASS="ballerselite40"
export MQTT_TOPIC="scribe/transcripts"

echo "MQTT environment variables set:"
echo "  MQTT_BROKER_HOST=$MQTT_BROKER_HOST"
echo "  MQTT_BROKER_PORT=$MQTT_BROKER_PORT"
echo "  MQTT_USER=$MQTT_USER"
echo "  MQTT_TOPIC=$MQTT_TOPIC"
echo "--------------------------------------------------------"

# --------------------------------------------------------
# 2) System Dependencies
# --------------------------------------------------------
echo "Updating package lists..."
sudo apt-get update

echo "Installing system dependencies..."
sudo apt-get install -y \
  ffmpeg \
  libportaudio2 \
  python3 \
  python3-dev \
  build-essential \
  libffi-dev \
  python3-pip \
  git \
  cmake \
  python3-venv

# --------------------------------------------------------
# 3) Create & Activate Python Virtual Environment
# --------------------------------------------------------
if [ ! -d "venv" ]; then
    echo "Creating a new virtual environment in ./venv ..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

# --------------------------------------------------------
# 4) Upgrade pip in the venv, Install Python Dependencies
# --------------------------------------------------------
echo "Upgrading pip inside the virtual environment..."
pip install --upgrade pip

echo "Installing Python dependencies from requirements.txt (in venv)..."
pip install -r requirements.txt

# (Optional) ensure `scipy` is installed (if not already in requirements.txt)
pip install scipy

# --------------------------------------------------------
# 5) Prepare whisper.cpp
# --------------------------------------------------------
if [ ! -d "whisper.cpp" ]; then
  echo "Cloning whisper.cpp repository..."
  git clone https://github.com/ggerganov/whisper.cpp.git
else
  echo "whisper.cpp directory exists, skipping clone."
fi

# Check if whisper-cli binary is built
if [ ! -f "whisper.cpp/build/bin/whisper-cli" ]; then
  echo "whisper.cpp is not built or 'whisper-cli' missing. Building now..."
  cd whisper.cpp

  # Clean old build if partial
  if [ -d "build" ]; then
    rm -rf build
  fi

  cmake -B build
  cmake --build build --config Release
  cd ..
else
  echo "whisper.cpp build exists, skipping build."
fi

# Check if the tiny.en model is present
# The downloaded file is typically named "ggml-tiny.en.bin" in whisper.cpp/models
if [ ! -f "whisper.cpp/models/ggml-tiny.en.bin" ]; then
  echo "tiny.en model not found, downloading..."
  cd whisper.cpp
  ./models/download-ggml-model.sh tiny.en
  cd ..
else
  echo "tiny.en model already exists, skipping download."
fi

# --------------------------------------------------------
# 6) Run stt_processor.py in venv
# --------------------------------------------------------
echo "Launching STT Processor with MQTT environment variables..."
python stt_processor.py

echo "Done."
