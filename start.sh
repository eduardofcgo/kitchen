#!/bin/sh

systemctl restart cups

tmux kill-session -t kitchen
tmuxinator start
