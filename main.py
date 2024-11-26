from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging
from statsnet import StatsnetClient

# Инициализация приложения
app = FastAPI(
    title="Bitrix24 & Statsnet Integration",
    description="API для интеграции данных компании между Statsnet и Bitrix24",
    version="1.0.1",
)

# Константы
BITRIX_WEBHOOK_URL = "https://prodvig.bitrix24.kz/rest/1/ts9pegm640jua38a/"
STATSNET_API_KEY = "<y6440652f3245493044502e2375755a4c772a642eb685beec7674ddeac9fb251896e4030757ccec9f>"

# Логирование
logging.basicConfig(filename="logFile.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# Инициализация клиента Statsnet
statsnet_client = StatsnetClient(api_key=STATSNET_API_KEY)

# Модель данных
class CompanyRequest(BaseModel):
    company_id: int
    bin: Optional[str] = None
    phone: Optional[str] = None

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

    # Проверка входных данных
    if not data.bin and not data.phone:
        raise HTTPException(status_code=400, detail="Either 'bin' or 'phone' must be provided.")

    query_param = data.bin if data.bin else data.phone

    # Логирование запроса к Statsnet
    logging.info(f"Fetching company data from Statsnet: query_param={query_param}")

    try:
        # Получение данных компании из Statsnet с использованием SDK
        company_info = statsnet_client.business.search(query=query_param)

        # Проверка, что данные о компании найдены
        if not company_info:
            logging.info(f"No data found for company with query_param={query_param}")
            raise HTTPException(status_code=404, detail="Company not found in Statsnet API.")
        
        # Извлечение данных компании
        company_data = company_info[0]
        short_name = company_data.get("short_name", "N/A")
        full_name = company_data.get("full_name", "N/A")
        taxes = company_data.get("taxes", [])

        total_taxes = sum(t.get("amount", 0) for t in taxes)
        tax_2022 = next((t["amount"] for t in taxes if t["year"] == 2022), 0)

        # Логирование данных компании
        logging.info(f"Company data: short_name={short_name}, full_name={full_name}, total_taxes={total_taxes}, tax_2022={tax_2022}")

        # Обновление данных в Bitrix24
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

        # Проверка ответа от Bitrix24
        if bitrix_response.status_code != 200 or not bitrix_response.json().get("result"):
            logging.error(f"Bitrix24 API error: {bitrix_response.text}")
            raise HTTPException(status_code=500, detail="Failed to update data in Bitrix24.")

        # Успешный ответ
        return {
            "status": "success",
            "short_name": short_name,
            "full_name": full_name,
            "total_taxes": total_taxes,
            "tax_2022": tax_2022,
        }

    except Exception as e:
        logging.error(f"Error fetching company data from Statsnet: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
