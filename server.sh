rm -f /tmp/llama.log
caffeinate /opt/homebrew/bin/llama-server -t 4 --mlock --ctx-checkpoints 0 -ngl 99 -m $PWD/Qwen3-4B-Instruct-2507-Q4_K_M.gguf --port 8000 --host localhost --parallel 1 --cache-ram 0 -c 8192 -b 2048 -ub 2048 -sps 0.0 --log-file /tmp/llama.log
