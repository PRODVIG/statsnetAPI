from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
from statsnet_python_sdk import Client  # Импорт SDK Statsnet
import requests
import logging

# Инициализация приложения
app = FastAPI(
    title="Bitrix24 & Statsnet Integration",
    description="API для интеграции данных компании между Statsnet и Bitrix24",
    version="1.0.1",
)

# Константы
BITRIX_WEBHOOK_URL = "https://prodvig.bitrix24.kz/rest/1/ts9pegm640jua38a/"
STATSNET_API_KEY = "<y6440652f3245493044502e2375755a4c772a642eb685beec7674ddeac9fb251896e4030757ccec9f>"  # Убедитесь, что ключ действителен

# Логирование
logging.basicConfig(filename="logFile.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# Модель данных
class CompanyRequest(BaseModel):
    company_id: int
    bin: Optional[str] = None  # БИН компании
    phone: Optional[str] = None  # Телефон компании (опционально)

# Инициализация клиента Statsnet
client = Client(STATSNET_API_KEY)

# Обработчик запроса
@app.post("/company", summary="Обновление данных компании", tags=["Bitrix24"])
async def handle_company(data: CompanyRequest):
    """
    Получение данных о компании из Statsnet и обновление их в Bitrix24.

    - **company_id**: ID компании в Bitrix24
    - **bin**: БИН компании (опционально)
    - **phone**: Номер телефона компании (опционально)
    """
    company_id = data.company_id

    # Проверка, что хотя бы одно поле поиска передано
    if not data.bin and not data.phone:
        raise HTTPException(status_code=400, detail="Either 'bin' or 'phone' must be provided.")

    # Определяем параметр поиска
    if data.bin:
        logging.info(f"Поиск компании по БИН: {data.bin}")
        try:
            # Явный поиск по идентификатору (БИН)
            company = client.get_company_by_identifier(data.bin)
        except Exception as e:
            logging.error(f"Ошибка поиска по БИН: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Statsnet API error: {str(e)}")
    else:
        logging.info(f"Поиск компании по телефону: {data.phone}")
        try:
            # Общий поиск по телефону через query
            companies = client.search(query=data.phone, jurisdiction="kz", limit=1)
            if not companies or not companies.get("data"):
                raise HTTPException(status_code=404, detail="Компания не найдена.")
            company = companies["data"][0]
        except Exception as e:
            logging.error(f"Ошибка поиска компании: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Statsnet API error: {str(e)}")

    # Проверяем полученные данные
    if not company:
        logging.info("Компания не найдена.")
        raise HTTPException(status_code=404, detail="Компания не найдена.")

    # Извлекаем данные
    short_name = company.get("short_name", "N/A")
    full_name = company.get("full_name", "N/A")
    taxes = company.get("taxes", [])
    total_taxes = sum(t.get("amount", 0) for t in taxes)
    tax_2022 = next((t["amount"] for t in taxes if t["year"] == 2022), 0)

    # Логируем данные компании
    logging.info(f"Данные компании: short_name={short_name}, full_name={full_name}, total_taxes={total_taxes}, tax_2022={tax_2022}")

    # Обновление данных в Bitrix24
    try:
        bitrix_response = requests.post(
            f"{BITRIX_WEBHOOK_URL}crm.company.update",
            json={
                "id": company_id,
                "fields": {
                    "UF_CRM_SHORT_NAME": short_name,
                    "UF_CRM_FULL_NAME": full_name,
                    "UF_CRM_TAX_2022": tax_2022,
                    "UF_CRM_TOTAL_TAXES": total_taxes,
                    "UF_CRM_STATSNET_URL": f"https://statsnet.co/companies/kz/{data.bin}",
                },
            },
        )

        if bitrix_response.status_code != 200 or not bitrix_response.json().get("result"):
            raise Exception(f"Ошибка Bitrix24 API: {bitrix_response.text}")
    except Exception as e:
        logging.error(f"Ошибка при обновлении в Bitrix24: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update data in Bitrix24.")

    # Возвращаем успешный ответ
    return {
        "status": "success",
        "short_name": short_name,
        "full_name": full_name,
        "total_taxes": total_taxes,
        "tax_2022": tax_2022,
    }
