from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import logging
import json

# Настройка логирования
logging.basicConfig(filename="logFile.txt", level=logging.INFO, format="%(asctime)s - %(message)s")

# Инициализация FastAPI
app = FastAPI(
    title="Bitrix24 & Statsnet Integration",
    description="API для интеграции данных между Statsnet и Bitrix24",
    version="1.0.1",
)

# Константы
BITRIX_WEBHOOK_URL = "https://prodvig.bitrix24.kz/rest/1/ts9pegm640jua38a/"
STATSNET_API_URL = "https://statsnet.co/search/kz/"

# Параметры для Bitrix24
statsnet_url_link_field = "UF_CRM_1679854080"
statsnet_tax_total_field = "UF_CRM_1679854136"
statsnet_tax_2022_field = "UF_CRM_1679854188"
statsnet_tax_total_money_field = "UF_CRM_1680100714"
statsnet_tax_2022_money_field = "UF_CRM_1680100777"
statsnet_shortName_field = "UF_CRM_1681246853"
statsnet_fullName_field = "UF_CRM_1681246872"

# Модели данных
class CompanyRequest(BaseModel):
    company_id: int
    bin: str

# Функция для выполнения CURL-запроса
def curl_request(url: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0',
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        logging.error(f"Error during HTTP request: {e}")
        return None

# Главный обработчик API
@app.post("/company")
async def update_company(data: CompanyRequest):
    company_id = data.company_id
    bin_code = data.bin

    if not bin_code:
        raise HTTPException(status_code=400, detail="BIN must be provided.")

    statsnet_url_link = f"{STATSNET_API_URL}{bin_code}"

    logging.info(f"Requesting Statsnet data for BIN: {bin_code}")

    req = curl_request(statsnet_url_link)

    if req:
        try:
            # Пытаемся извлечь данные из JSON-ответа
            match = re.search(r'__NEXT_DATA__" type="application/json">(.*?)<', req)
            if match:
                json_result = json.loads(match.group(1))
                company_data = json_result["props"]["pageProps"]["company"]["company"]

                # Извлечение необходимых данных
                statsnet_shortName = company_data["title"]
                statsnet_fullName = company_data["name"]
                financials = company_data["financials"]

                statsnet_tax_2022 = 0
                statsnet_tax_total = 0

                # Обработка финансовых данных
                for tax in financials:
                    if tax["year"] == 2022:
                        statsnet_tax_2022 = tax["taxes"]
                    statsnet_tax_total += tax["taxes"]

                # Подготовка данных для обновления Bitrix24
                fields = {
                    statsnet_url_link_field: statsnet_url_link,
                    statsnet_tax_total_field: statsnet_tax_total,
                    statsnet_tax_2022_field: statsnet_tax_2022,
                    statsnet_tax_total_money_field: statsnet_tax_total,
                    statsnet_tax_2022_money_field: statsnet_tax_2022,
                    statsnet_shortName_field: statsnet_shortName,
                    statsnet_fullName_field: statsnet_fullName,
                }

                # Обновление компании в Bitrix24
                bitrix_response = requests.post(
                    f"{BITRIX_WEBHOOK_URL}crm.company.update",
                    json={
                        "id": company_id,
                        "fields": fields
                    },
                )

                if bitrix_response.status_code == 200 and bitrix_response.json().get("result"):
                    logging.info(f"Company data successfully updated in Bitrix24.")
                    return {"status": "success", "message": "Company data updated in Bitrix24"}

                else:
                    logging.error(f"Failed to update company in Bitrix24: {bitrix_response.text}")
                    raise HTTPException(status_code=500, detail="Failed to update company in Bitrix24.")

            else:
                logging.error("Failed to extract company data from Statsnet.")
                raise HTTPException(status_code=500, detail="Failed to extract company data from Statsnet.")

        except Exception as e:
            logging.error(f"Error processing Statsnet data: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing Statsnet data: {str(e)}")
    else:
        logging.error(f"Failed to get data from Statsnet for BIN: {bin_code}")
        raise HTTPException(status_code=500, detail="Failed to get data from Statsnet.")

