import cloudscraper

scraper = cloudscraper.create_scraper()  # Создаёт объект с поддержкой обхода Cloudflare
url = "https://statsnet.co/api/v2/auth/check"
headers = {
    "Authorization": "Bearer 6440652f3245493044502e2375755a4c772a642eb685beec7674ddeac9fb251896e4030757ccec9f",
    "Content-Type": "application/json",
}

response = scraper.get(url, headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Response Text: {response.text}")
