@echo off
chcp 65001 > nul
echo ======================================================================
echo LAUNCHING SMART SEARCH DOCUMENT STORAGE ECOSYSTEM
echo ======================================================================
echo.

echo [1/4] Checking and preparing configuration files...
if not exist .env (
    if exist .env.example (
        copy .env.example .env > nul
        echo [OK] Configuration file .env successfully created from template.
    ) else (
        echo [CRITICAL ERROR] Template file .env.example not found!
        echo Deployment aborted.
        pause
        exit /b
    )
) else (
    echo [INFO] Configuration file .env already exists. Using current settings.
)
echo.

echo [2/4] Removing old conflicting containers...
docker compose down

echo [3/4] Starting Docker Compose containers and building backend...
docker compose up --build -d

echo.
echo [4/4] System is deploying in the background!
echo Please wait 1-2 minutes for the loader to download the AI model weights.
echo.
echo Once the download is complete, the project will be available at:
echo - Client Interface: http://localhost:8085/
echo - Admin Dashboard:  http://localhost:8085/admin
echo.
echo To view the AI model download progress, press any key...
pause > nul
docker logs -f smart_search_model_loader