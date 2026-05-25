#!/usr/bin/env bash
# Create conda env for CLRNet + MUFLD dataset
set -euo pipefail

ENV_NAME="${CLRNET_ENV_NAME:-clrnet_lane}"
CLRNET_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

source "$(conda info --base)/etc/profile.d/conda.sh"

if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
  echo "Env $ENV_NAME exists, activate: conda activate $ENV_NAME"
else
  conda create -n "$ENV_NAME" python=3.8 -y
fi
conda activate "$ENV_NAME"

# PyTorch (adjust CUDA version to match your driver)
pip install torch==1.10.2+cu113 torchvision==0.11.3+cu113 \
  -f https://download.pytorch.org/whl/cu113/torch_stable.html

pip install mmcv-full==1.4.0 -f https://download.openmmlab.com/mmcv/dist/cu113/torch1.10/index.html

pip install -r "$CLRNET_ROOT/requirements.txt"

cd "$CLRNET_ROOT"
python setup.py develop

echo ""
echo "Done. Usage:"
echo "  conda activate $ENV_NAME"
echo "  cd $CLRNET_ROOT"
echo "  python main.py configs/clrnet/clr_resnet18_mufld_smoke.py --gpus 0"
