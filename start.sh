echo "======================================================================"
echo "LAUNCHING SMART SEARCH DOCUMENT STORAGE ECOSYSTEM"
echo "======================================================================"
echo

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "[OK] Configuration file .env successfully created."
    else
        echo "[ERROR] Template file .env.example not found!"
        exit 1
    fi
fi

echo "Removing old containers..."
docker compose down

echo "Building backend and launching the stack..."
docker compose up --build -d

echo "Tracking AI model download progress..."
docker logs -f smart_search_model_loader
