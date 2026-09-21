#!/usr/bin/env bash

# ===============================================================================
# StageBridge Model Setup Script
# Downloads and extracts the default Sherpa-ONNX streaming Zipformer model
# ===============================================================================

set -e

MODEL_NAME="sherpa-onnx-streaming-zipformer-en-2023-06-21"
TARGET_DIR="python/models/${MODEL_NAME}"
ARCHIVE_NAME="${MODEL_NAME}.tar.bz2"
DOWNLOAD_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/${ARCHIVE_NAME}"

# Ensure models directory exists
mkdir -p python/models

# Check if model already exists
if [ -f "${TARGET_DIR}/encoder-epoch-99-avg-1.int8.onnx" ]; then
    echo "[INFO] Model '${MODEL_NAME}' is already downloaded and ready."
    exit 0
fi

echo "[INFO] Downloading ${MODEL_NAME}..."
curl -L --progress-bar "${DOWNLOAD_URL}" -o "python/models/${ARCHIVE_NAME}"

echo "[INFO] Extracting archive..."
tar -jxvf "python/models/${ARCHIVE_NAME}" -C python/models/

echo "[INFO] Cleaning up compressed archive..."
rm "python/models/${ARCHIVE_NAME}"

echo "[SUCCESS] Model installed successfully to ${TARGET_DIR}"