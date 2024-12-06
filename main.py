from fastapi import FastAPI, HTTPException, Query
import httpx
import json

# Конфигурация Bitrix24
BITRIX_WEBHOOK_URL = "https://prodvig.bitrix24.kz/rest/1/ts9pegm640jua38a/"

# Создаем приложение FastAPI
app = FastAPI()

# Заголовки для имитации браузера
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

# Лог-файл
LOG_FILE = "logFile.txt"

def log_message(message: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


@app.post("/process_company/")
async def process_company(company_id: int = Query(...), bin_number: str = Query(...)):
    """
    Обработка компании: получение данных по BIN и обновление в Bitrix24.
    """
    try:
        # URL для поиска по BIN
        search_url = f"https://statsnet.co/search/kz/{bin_number}"
        
        # 1. Запрос к statsnet.co
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            response = await client.get(search_url)

        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Ошибка получения данных: {response.status_code}")

        # Логирование ответа
        log_message(f"Ответ от statsnet.co (поиск): {response.text}")

        # Извлечение JSON из ответа
        matches = response.text.find("__NEXT_DATA__")
        if matches == -1:
            raise HTTPException(status_code=400, detail="Данные не найдены в ответе.")

        # Извлекаем и декодируем JSON
        json_data_start = response.text.find(">", matches) + 1
        json_data_end = response.text.find("</script>", json_data_start)
        raw_json = response.text[json_data_start:json_data_end]
        json_result = json.loads(raw_json)

        # 2. Проверяем наличие компании
        companies = json_result.get("props", {}).get("pageProps", {}).get("companies", [])
        if not companies:
            raise HTTPException(status_code=400, detail="Компания с указанным BIN не найдена.")

        # Получаем ID компании
        company_data = companies[0]
        statsnet_id = company_data.get("id")
        if not statsnet_id:
            raise HTTPException(status_code=400, detail="Не удалось получить ID компании.")

        # 3. Запрос детальной информации
        details_url = f"https://statsnet.co/companies/kz/{statsnet_id}"
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            details_response = await client.get(details_url)

        if details_response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Ошибка получения деталей компании: {details_response.status_code}")

        # Логирование ответа
        log_message(f"Ответ от statsnet.co (детали): {details_response.text}")

        # Извлечение JSON из ответа
        matches = details_response.text.find("__NEXT_DATA__")
        if matches == -1:
            raise HTTPException(status_code=400, detail="Детали компании не найдены в ответе.")

        # Извлекаем и декодируем JSON
        json_data_start = details_response.text.find(">", matches) + 1
        json_data_end = details_response.text.find("</script>", json_data_start)
        raw_json = details_response.text[json_data_start:json_data_end]
        details_json = json.loads(raw_json)

        company_details = details_json.get("props", {}).get("pageProps", {}).get("company", {}).get("company", {})
        if not company_details:
            raise HTTPException(status_code=400, detail="Не удалось извлечь детали компании.")

        # 4. Извлечение нужных данных
        statsnet_shortName = company_details.get("title", "")
        statsnet_fullName = company_details.get("name", "")
        financials = company_details.get("financials", [])

        statsnet_tax_total = sum(tax.get("taxes", 0) for tax in financials)
        statsnet_tax_2022 = sum(tax.get("taxes", 0) for tax in financials if tax.get("year") == 2022)

        # Логируем данные
        log_message(f"Детали компании: {company_details}")

        # 5. Формируем данные для Bitrix24
        fields = {
            "fields": {
                "UF_CRM_1679854080": search_url,
                "UF_CRM_1679854136": statsnet_tax_total,
                "UF_CRM_1679854188": statsnet_tax_2022,
                "UF_CRM_1680100714": statsnet_tax_total,
                "UF_CRM_1680100777": statsnet_tax_2022,
                "UF_CRM_1681246853": statsnet_shortName,
                "UF_CRM_1681246872": statsnet_fullName,
            }
        }

        # 6. Обновление компании в Bitrix24
        bitrix_url = f"{BITRIX_WEBHOOK_URL}crm.company.update?ID={company_id}"
        async with httpx.AsyncClient(headers=HEADERS, timeout=15) as client:
            bitrix_response = await client.post(bitrix_url, json=fields)

        if bitrix_response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Ошибка обновления данных в Bitrix24: {bitrix_response.status_code}")

        log_message(f"Обновление в Bitrix24: {bitrix_response.text}")

        return {"status": "success", "message": "Данные компании успешно обновлены."}

    except Exception as e:
        log_message(f"Ошибка: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))