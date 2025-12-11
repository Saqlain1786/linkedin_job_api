from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import os

app = Flask(__name__)

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(
        executable_path=ChromeDriverManager().install(),
        options=chrome_options
    )
    return driver


@app.get("/search")
def search():
    keyword = request.args.get("keyword", "service desk")
    limit = int(request.args.get("limit", 50))

    url = f"https://www.linkedin.com/jobs/search/?keywords={keyword}"

    driver = create_driver()
    driver.get(url)
    time.sleep(5)

    jobs = []
    cards = driver.find_elements(By.CLASS_NAME, "base-card")

    for c in cards[:limit]:
        try:
            title = c.find_element(By.CLASS_NAME, "base-search-card__title").text
            company = c.find_element(By.CLASS_NAME, "base-search-card__subtitle").text
            location = c.find_element(By.CLASS_NAME, "job-search-card__location").text
            jobUrl = c.find_element(By.TAG_NAME, "a").get_attribute("href")

            jobs.append({
                "title": title,
                "company": company,
                "location": location,
                "jobUrl": jobUrl
            })
        except:
            pass

    driver.quit()

    return jsonify({
        "total": len(jobs),
        "jobs": jobs
    })


@app.get("/")
def home():
    return {"status": "LinkedIn Scraper API live"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
