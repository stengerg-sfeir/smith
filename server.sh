caffeinate -i -s python3 -m mlx_lm.server \
  --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --port 8000 \
  --host localhost \
  --max-tokens 8192

