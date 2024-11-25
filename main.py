from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import logging

# Инициализация приложения FastAPI
app = FastAPI(
    title="Bitrix24 & Statsnet Integration",
    description="API для интеграции данных компании между Statsnet и Bitrix24",
    version="1.0.1",
)

# Константы
BITRIX_WEBHOOK_URL = "webhook"
STATSNET_API_URL = "https://statsnet.co/api/v2"
STATSNET_HEADERS = {"Authorization": "Bearer <api key"}

# Логирование
logging.basicConfig(filename="logFile.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# Модель запроса
class CompanyRequest(BaseModel):
    company_id: int
    bin: str | None = None
    phone: str | None = None  # Новый параметр для поиска по телефону

# Эндпоинт для обработки данных
@app.post("/company", summary="Обновление данных компании", tags=["Bitrix24"])
async def handle_company(data: CompanyRequest):
    """
    Получение данных о компании из Statsnet и обновление их в Bitrix24.

    - **company_id**: ID компании в Bitrix24
    - **bin**: БИН компании (опционально)
    - **phone**: Номер телефона компании (опционально)
    """
    company_id = data.company_id

    # Проверка на наличие хотя бы одного параметра поиска
    if not data.bin and not data.phone:
        raise HTTPException(status_code=400, detail="Either 'bin' or 'phone' must be provided.")

    # Шаг 1: Поиск компании в Statsnet по БИН или телефону
    query_param = data.bin if data.bin else data.phone
    search_field = "query" if data.bin else "phone"
    statsnet_response = requests.get(
        f"{STATSNET_API_URL}/business/search",
        params={search_field: query_param},
        headers=STATSNET_HEADERS,
    )

    if statsnet_response.status_code != 200:
        logging.error(f"Statsnet API error: {statsnet_response.json()}")
        raise HTTPException(status_code=500, detail="Failed to fetch data from Statsnet API.")

    statsnet_data = statsnet_response.json()

    # Шаг 2: Проверка данных
    if not statsnet_data.get("data"):
        logging.info(f"No company found with {search_field}: {query_param}")
        raise HTTPException(status_code=404, detail="Company not found in Statsnet API.")

    company_info = statsnet_data["data"][0]  # Первый результат поиска
    short_name = company_info.get("short_name", "N/A")
    full_name = company_info.get("full_name", "N/A")
    taxes = company_info.get("taxes", [])

    # Подсчет налогов
    total_taxes = sum(t.get("amount", 0) for t in taxes)
    tax_2022 = next((t["amount"] for t in taxes if t["year"] == 2022), 0)

    # Шаг 3: Отправка данных в Bitrix24
    bitrix_response = requests.post(
        f"{BITRIX_WEBHOOK_URL}crm.company.update",
        json={
            "id": company_id,
            "fields": {
                "UF_CRM_SHORT_NAME": short_name,
                "UF_CRM_FULL_NAME": full_name,
                "UF_CRM_TAX_2022": tax_2022,
                "UF_CRM_TOTAL_TAXES": total_taxes,
                "UF_CRM_STATSNET_URL": f"https://statsnet.co/companies/kz/{query_param}",
            },
        },
    )

    if bitrix_response.status_code != 200:
        logging.error(f"Bitrix24 API error: {bitrix_response.json()}")
        raise HTTPException(status_code=500, detail="Failed to update data in Bitrix24.")

    return {
        "status": "success",
        "short_name": short_name,
        "full_name": full_name,
        "total_taxes": total_taxes,
        "tax_2022": tax_2022,
    }
