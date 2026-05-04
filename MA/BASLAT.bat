@echo off
chcp 65001 >nul
title OKYISS - Backend + Frontend
cd /d "%~dp0"
echo.
echo Klasor: %CD%
echo.
if not exist "package.json" (
  echo HATA: Bu dosyayi MA proje klasorunun ICINE koyun (package.json yaninda olsun).
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo HATA: Node.js yuklu degil veya PATH'te yok. https://nodejs.org adresinden kurun.
  pause
  exit /b 1
)
if not exist "node_modules\concurrently" (
  echo Ilk kurulum: npm install ...
  call npm install
)
echo Sunucular basliyor (api + node + web). Kapatmak icin Ctrl+C
echo Tarayicida Vite adresini acin (ornek: http://localhost:5173)
echo.
call npm run dev
pause
