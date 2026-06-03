#!/usr/bin/env bash
# CPU-friendly env for CLRNet ONNX export (no CUDA required for export).
set -euo pipefail

ENV_NAME="${CLRNET_EXPORT_ENV:-clrnet_export}"
CLRNET_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

source "$(conda info --base)/etc/profile.d/conda.sh"

if ! conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  conda create -n "$ENV_NAME" python=3.8 -y
fi
conda activate "$ENV_NAME"

pip install --upgrade pip
pip install torch==1.10.2+cpu torchvision==0.11.3+cpu \
  -f https://download.pytorch.org/whl/cpu/torch_stable.html
pip install mmcv-full==1.4.0 -f https://download.openmmlab.com/mmcv/dist/cpu/torch1.10/index.html
pip install onnx onnxruntime onnxsim
pip install -r "$CLRNET_ROOT/requirements.txt"
cd "$CLRNET_ROOT"
pip install -e .

echo ""
echo "Export ONNX:"
echo "  conda activate $ENV_NAME"
echo "  cd $CLRNET_ROOT"
echo "  python tools/export_onnx.py --check"
