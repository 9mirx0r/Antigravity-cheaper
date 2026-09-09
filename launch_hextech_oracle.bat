@echo off
title Hextech Oracle Launcher
cd /d "%~dp0benchmarks\porofesor_itero_benchmark\variants\token_guard"
"C:\Users\emir\AppData\Local\Programs\Python\Python314\python.exe" main.py
if errorlevel 1 (
    echo.
    echo Execution failed with errorlevel %errorlevel%
    pause
)
