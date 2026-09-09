@echo off
title VIUStudio Cloudflare Workers API
echo ==========================================
echo Starting VIUStudio Cloudflare API (Wrangler)
echo URL: http://localhost:8787
echo ==========================================
cd /d "%~dp0web"
npm run dev:api
pause
