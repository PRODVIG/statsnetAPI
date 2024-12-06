# Используем официальный образ Python как базовый
FROM python:3.9-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Устанавливаем зависимости для Playwright
RUN apt-get update && apt-get install -y \
    libnss3 \
    libxss1 \
    libasound2 \
    libatk1.0-0 \
    libpangocairo-1.0-0 \
    libx11-xcb1 \
    libxcomposite1 \
    libxcursor1 \
    libxdamage1 \
    libxi6 \
    libgbm1 \
    libgtk-3-0 \
    libfontconfig1 \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем Playwright и необходимые браузеры
RUN pip install playwright && playwright install --with-deps

# Копируем файл зависимостей в контейнер
COPY requirements.txt .

# Устанавливаем зависимости из requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь проект в контейнер
COPY . .

# Открываем порт, на котором будет работать FastAPI (по умолчанию это 8000)
EXPOSE 8000

# Указываем команду для запуска FastAPI с помощью Uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]