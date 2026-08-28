@echo off
cd /d "%~dp0"
python main.py --scheduled >> "logs\scheduled.log" 2>&1
