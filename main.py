from fastapi import FastAPI, HTTPException, Query
import httpx
import time
import json
from typing import Optional

app = FastAPI()

B24_WEBHOOK_URL = 'https://prodvig.bitrix24.kz/rest/1/ts9pegm640jua38a/'
COOKIE_FILE = './cookies.txt'

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1"
}

LOG_FILE = './logFile.txt'


def log_message(message: str):
    """Записываем сообщение в лог-файл."""
    with open(LOG_FILE, 'a', encoding='utf-8') as log:
        log.write(f"{message}\n")


async def fetch_with_retries(url: str, retries: int = 3, delay: int = 30) -> str:
    """Выполняем HTTP-запрос с повторными попытками."""
    async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True) as client:
        for attempt in range(retries):
            try:
                response = await client.get(url)
                if response.status_code == 503 and attempt < retries - 1:
                    time.sleep(delay)
                else:
                    response.raise_for_status()
                    return response.text
            except httpx.HTTPStatusError as e:
                if attempt == retries - 1:
                    log_message(f"Ошибка HTTP-запроса: {e}")
                    raise HTTPException(status_code=503, detail=f"Не удалось получить данные из {url}.")
    return ""


async def update_bitrix(company_id: str, fields: dict):
    """Обновляем данные в Битрикс."""
    url = f"{B24_WEBHOOK_URL}crm.company.update"
    payload = {
        "id": company_id,
        "fields": fields
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


@app.get("/update_company/")
async def update_company(company_id: str, bin: str):
    """Основная функция для обновления данных компании."""
    log_message(f"Запрос обновления для компании ID: {company_id}, BIN: {bin}")

    # URL для поиска компании по BIN
    search_url = f"https://statsnet.co/search/kz/{bin}"
    search_response = await fetch_with_retries(search_url)

    # Парсинг ответа для получения ID Statsnet
    try:
        search_json = json.loads(search_response.split('__NEXT_DATA__" type="application/json">')[1].split("</script>")[0])
        statsnet_id = search_json["props"]["pageProps"]["companies"][0]["id"]
    except (IndexError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=404, detail="Не удалось получить данные компании по BIN.")

    # URL для детальной информации о компании
    detail_url = f"https://statsnet.co/companies/kz/{statsnet_id}"
    detail_response = await fetch_with_retries(detail_url)

    # Парсинг детальной информации
    try:
        detail_json = json.loads(detail_response.split('__NEXT_DATA__" type="application/json">')[1].split("</script>")[0])
        company_data = detail_json["props"]["pageProps"]["company"]["company"]
        statsnet_shortName = company_data.get("title", "")
        statsnet_fullName = company_data.get("name", "")
        financials = company_data.get("financials", [])

        # Расчёт налогов
        statsnet_tax_2022 = sum(tax["taxes"] for tax in financials if tax.get("year") == 2022)
        statsnet_tax_total = sum(tax["taxes"] for tax in financials)
    except (IndexError, KeyError, json.JSONDecodeError):
        raise HTTPException(status_code=500, detail="Ошибка парсинга деталей компании.")

    # Логирование полученных данных
    log_message(f"Детали компании:\nShortName: {statsnet_shortName}, FullName: {statsnet_fullName}")
    log_message(f"Налоги: Общий - {statsnet_tax_total}, За 2022 год - {statsnet_tax_2022}")

    # Формирование полей для Битрикс
    fields = {
        "UF_CRM_1679854080": detail_url,  # Ссылка на компанию
        "UF_CRM_1681246853": statsnet_shortName,  # Краткое название
        "UF_CRM_1681246872": statsnet_fullName,  # Полное название
        "UF_CRM_1679854136": statsnet_tax_total,  # Общий налог
        "UF_CRM_1679854188": statsnet_tax_2022,  # Налог за 2022
    }

    # Обновляем данные в Битрикс
    bitrix_response = await update_bitrix(company_id, fields)
    log_message(f"Ответ Битрикс: {bitrix_response}")

    return {"status": "success", "bitrix_response": bitrix_response}