from fastapi import FastAPI, HTTPException, Query
import requests
import os
import logging
import json
from typing import Optional

# Настройка логирования
LOG_FILE = os.path.join(os.path.dirname(__file__), 'logFile.txt')
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Константы
B24_WEBHOOK_URL = ''
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Cache-Control': 'max-age=0'
}


# FastAPI приложение
app = FastAPI(title="Bitrix24 + StatsNet API", version="1.0")

# Методы для взаимодействия с Bitrix24 API
class Bitrix24Api2:
    def __init__(self, webhook_url, log_file):
        self.webhook_url = webhook_url
        self.log_file = log_file

    def company_get(self, company_id):
        url = f"{self.webhook_url}crm.company.get"
        response = requests.post(url, headers=HEADERS, json={'id': company_id})
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Ошибка получения компании: {response.text}")
            return None

    def company_update(self, company_id, fields):
        url = f"{self.webhook_url}crm.company.update"
        response = requests.post(url, headers=HEADERS, json={'id': company_id, 'fields': fields})
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Ошибка обновления компании: {response.text}")
            return None

    def send_comment(self, company_id, comment, entity_type):
        url = f"{self.webhook_url}crm.timeline.comment.add"
        response = requests.post(url, headers=HEADERS, json={
            'fields': {
                'ENTITY_ID': company_id,
                'ENTITY_TYPE': entity_type,
                'COMMENT': comment
            }
        })
        if response.status_code != 200:
            logging.error(f"Ошибка отправки комментария: {response.text}")

# Методы для взаимодействия с StatsNet
def fetch_statsnet_data(bin_code):
    bin_code = ''.join(filter(str.isdigit, bin_code))
    search_url = f"https://statsnet.co/search/kz/{bin_code}"
    
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        if response.status_code == 200:
            return response.text
        else:
            logging.error(f"Ошибка запроса к StatsNet: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка подключения к StatsNet: {e}")
        return None

def parse_statsnet_data(response):
    try:
        start_index = response.find('__NEXT_DATA__" type="application/json">') + len('__NEXT_DATA__" type="application/json">')
        end_index = response.find('</script>', start_index)
        data_json = response[start_index:end_index]
        return json.loads(data_json)
    except Exception as e:
        logging.error(f"Ошибка парсинга данных: {e}")
        return None

# Основной обработчик
def process_company_data(company_id: int, bin_code: str):
    b24 = Bitrix24Api2(B24_WEBHOOK_URL, LOG_FILE)
    company_data = b24.company_get(company_id)

    if not company_data:
        raise HTTPException(status_code=404, detail="Компания не найдена в Bitrix24")

    statsnet_data = fetch_statsnet_data(bin_code)
    if not statsnet_data:
        raise HTTPException(status_code=500, detail="Ошибка при запросе к StatsNet")

    parsed_data = parse_statsnet_data(statsnet_data)
    if not parsed_data:
        raise HTTPException(status_code=500, detail="Ошибка обработки данных StatsNet")

    try:
        statsnet_id = parsed_data['props']['pageProps']['companies'][0]['id']
        details_url = f"https://statsnet.co/companies/kz/{statsnet_id}"
        logging.info(f"StatsNet URL: {details_url}")

        short_name = parsed_data['props']['pageProps']['company']['company']['title']
        full_name = parsed_data['props']['pageProps']['company']['company']['name']

        financials = parsed_data['props']['pageProps']['company']['company']['financials']
        tax_2022 = sum(f['taxes'] for f in financials if f['year'] == 2022)
        total_taxes = sum(f['taxes'] for f in financials)

        fields = {
            "UF_CRM_1679854080": details_url,
            "UF_CRM_1679854136": total_taxes,
            "UF_CRM_1679854188": tax_2022,
            "UF_CRM_1681246853": short_name,
            "UF_CRM_1681246872": full_name,
        }

        update_result = b24.company_update(company_id, fields)
        if update_result and update_result.get('result'):
            comment = f"Данные из StatsNet:\n- Taxes 2022: {tax_2022}\n- Total Taxes: {total_taxes}"
            b24.send_comment(company_id, comment, 'company')

            logging.info(f"Успешно обновлены данные компании {company_id}")
            return {"status": "success", "message": "Данные успешно обновлены", "fields": fields}
        else:
            raise HTTPException(status_code=500, detail="Ошибка обновления компании в Bitrix24")
    except Exception as e:
        logging.error(f"Ошибка обработки данных: {e}")
        raise HTTPException(status_code=500, detail="Ошибка обработки данных StatsNet")

# Эндпоинты FastAPI
@app.get("/")
def read_root():
    return {"message": "Добро пожаловать в API интеграции Bitrix24 и StatsNet"}

@app.post("/update_company")
def update_company(
    company_id: int = Query(..., description="ID компании в Bitrix24"),
    bin_code: str = Query(..., description="BIN компании")
):
    return process_company_data(company_id, bin_code)
