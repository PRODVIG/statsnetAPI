from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import cloudscraper
import logging

# Инициализация приложения
app = FastAPI(
    title="Bitrix24 & Statsnet Integration",
    description="API для интеграции данных компании между Statsnet и Bitrix24",
    version="1.0.1",
)

# Константы
BITRIX_WEBHOOK_URL = "https://prodvig.bitrix24.kz/rest/1/ts9pegm640jua38a/"
API_KEY = "6440652f3245493044502e2375755a4c772a642eb685beec7674ddeac9fb251896e4030757ccec9f"  
BASE_URL = "https://statsnet.co/api/v2/"

# Логирование
logging.basicConfig(filename="logFile.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# Создаём объект scraper для обхода Cloudflare
scraper = cloudscraper.create_scraper()

# Проверка авторизации
def check_authentication():
    try:
        response = scraper.get(f"{BASE_URL}auth/check", headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        })
        logging.info(f"Auth response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            logging.info("Authentication successful!")
            return response.json()
        else:
            logging.error(f"Failed to authenticate: {response.status_code} - {response.text}")
            raise HTTPException(status_code=401, detail=f"Authentication failed: {response.text}")
    except Exception as e:
        logging.error(f"Error during authentication: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal error during authentication")

# Модель данных для компании
class CompanyRequest(BaseModel):
    company_id: int
    bin: str | None = None
    phone: str | None = None

# Обработчик запроса для обновления данных компании
@app.post("/company", summary="Обновление данных компании", tags=["Bitrix24"])
async def handle_company(data: CompanyRequest):
    """
    Получение данных о компании из Statsnet и обновление их в Bitrix24.

    - **company_id**: ID компании в Bitrix24
    - **bin**: БИН компании (опционально)
    - **phone**: Номер телефона компании (опционально)
    """
    # Проверка авторизации
    check_authentication()

    company_id = data.company_id

    # Проверка входных данных
    if not data.bin and not data.phone:
        raise HTTPException(status_code=400, detail="Either 'bin' or 'phone' must be provided.")

    query_param = data.bin if data.bin else data.phone
    search_field = "query" if data.bin else "phone"

    # Логирование запроса к Statsnet
    logging.info(f"Fetching company data from Statsnet: {search_field}={query_param}")

    try:
        # Запрос к Statsnet через Cloudscraper
        response = scraper.get(
            f"{BASE_URL}business/search",
            params={search_field: query_param, "jurisdiction": "kz"},
            headers={
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
            }
        )
        logging.info(f"Statsnet response: {response.status_code} - {response.text}")

        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail=f"Statsnet API error: {response.text}")

        companies_data = response.json()
        if not companies_data:
            raise HTTPException(status_code=404, detail="Company not found in Statsnet.")

        company_info = companies_data[0]
        short_name = company_info.get("short_name", "N/A")
        full_name = company_info.get("full_name", "N/A")
        taxes = company_info.get("taxes", [])

        total_taxes = sum(t.get("amount", 0) for t in taxes)
        tax_2022 = next((t.get("amount", 0) for t in taxes if t.get("year") == 2022), 0)

        # Логирование данных компании
        logging.info(f"Company data: short_name={short_name}, full_name={full_name}, total_taxes={total_taxes}, tax_2022={tax_2022}")

    except Exception as e:
        logging.error(f"Error fetching company data from Statsnet: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Statsnet API error: {str(e)}")

    # Обновление данных в Bitrix24
    try:
        response = scraper.post(
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
            headers={"Content-Type": "application/json"}
        )
        logging.info(f"Bitrix24 response: {response.status_code} - {response.text}")

        if response.status_code != 200 or not response.json().get("result"):
            raise HTTPException(status_code=500, detail=f"Bitrix24 API error: {response.text}")
    except Exception as e:
        logging.error(f"Error updating data in Bitrix24: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Bitrix24 API error: {str(e)}")

    return {
        "status": "success",
        "short_name": short_name,
        "full_name": full_name,
        "total_taxes": total_taxes,
        "tax_2022": tax_2022,
    }
