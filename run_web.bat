@echo off
title VIUStudio Web Dev Server
echo ==========================================
echo Starting VIUStudio Web Frontend (Vite)
echo URL: http://localhost:3000
echo ==========================================
cd /d "%~dp0web"
npm run dev:frontend
pause
