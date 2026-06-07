echo "======================================================================"
echo "ЗАПУСК ЭКОСИСТЕМЫ ХРАНИЛИЩА ДОКУМЕНТОВ С УМНЫМ ПОИСКОМ"
echo "======================================================================"
echo

if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        cp .env.example .env
        echo "[OK] Файл конфигурации .env успешно создан."
    else
        echo "[ОШИБКА] Не найден .env.example!"
        exit 1
    fi
fi

echo "Очистка старых контейнеров..."
docker compose down

echo "Сборка бэкенда и запуск стека..."
docker compose up --build -d

echo "Отслеживание загрузки ИИ-модели..."
docker logs -f smart_search_model_loader