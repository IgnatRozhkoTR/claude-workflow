#!/bin/bash

# Status line with time and model information

# Parse JSON input
input=$(cat)
model=$(echo "$input" | jq -r '.model.display_name')

# Get current time
time=$(date +%H:%M)

# Build status line with emojis and separators
printf "🕐 \033[33m%s\033[0m | 🤖 \033[35m%s\033[0m ▶" "$time" "$model"