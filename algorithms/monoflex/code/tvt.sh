CUDA_VISIBLE_DEVICES=0 python tools/plain_train_net.py --batch_size 24 --config runs/monoflex.yaml --output output/exp2 --num_work 8
CUDA_VISIBLE_DEVICES=0 python tools/plain_train_net.py --config runs/monoflex.yaml --ckpt YOUR_CKPT  --eval --vis --num_work 0
