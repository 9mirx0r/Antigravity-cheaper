@echo off
title Hextech Oracle Launcher
cd /d "%~dp0benchmarks\porofesor_itero_benchmark\variants\token_guard"
python main.py
if errorlevel 1 (
    echo.
    echo Execution failed with errorlevel %errorlevel%
    pause
)
