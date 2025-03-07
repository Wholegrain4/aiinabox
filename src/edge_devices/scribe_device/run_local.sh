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

echo "Installing system dependencies (via apt)..."
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

echo "Activating virtual environment (no pip upgrade)..."
# This ensures that 'pip' and 'python' refer to the venv’s executables
source venv/bin/activate

# --------------------------------------------------------
# 4) Install Python Dependencies from requirements.txt
# --------------------------------------------------------
echo "Installing Python dependencies from requirements.txt (in venv)..."
pip install -r requirements.txt
# If 'scipy' is missing in requirements.txt but you need it:
# pip install scipy

# --------------------------------------------------------
# 5) Build whisper.cpp (if not already built)
# --------------------------------------------------------
if [ ! -d "whisper.cpp" ]; then
  echo "Cloning whisper.cpp repository..."
  git clone https://github.com/ggerganov/whisper.cpp.git
else
  echo "whisper.cpp directory exists, skipping clone."
fi

if [ ! -f "whisper.cpp/build/bin/whisper-cli" ]; then
  echo "No whisper-cli found; building whisper.cpp now..."
  cd whisper.cpp

  if [ -d "build" ]; then
    rm -rf build   # ensure a clean build
  fi

  cmake -B build
  cmake --build build --config Release

  cd ..
else
  echo "whisper.cpp build exists, skipping build."
fi

# Check if the tiny.en model is present
if [ ! -f "whisper.cpp/models/ggml-tiny.en.bin" ]; then
  echo "tiny.en model missing; downloading..."
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
