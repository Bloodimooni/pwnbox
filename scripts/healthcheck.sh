#!/bin/bash
echo "=== CorpChat Health Check ==="
echo "Timestamp: $(date)"
echo "Uptime: $(uptime -p)"
echo "Disk Usage: $(df -h / | tail -1)"
echo "Memory: $(free -m | grep Mem)"
echo "Python: $(python3 --version 2>&1)"
echo "Status: OK"
