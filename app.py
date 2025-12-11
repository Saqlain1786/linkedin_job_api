# app.py (replace existing)
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import os
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)

def create_driver():
    chrome_bin = os.environ.get("CHROME_BIN", "/usr/bin/chromium")
    chrome_options = Options()
    # Use headless chromium in a way compatible with newer Chrome
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.binary_location = chrome_bin

    # Use webdriver-manager to install a compatible chromedriver
    chromedriver_path = ChromeDriverManager(log_level=0).install()
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver

@app.get("/search")
def search():
    keyword = request.args.get("keyword", "service desk")
    limit = int(request.args.get("limit", 50))
    location = request.args.get("location", "")

    q = keyword.replace(" ", "%20")
    base_url = f"https://www.linkedin.com/jobs/search/?keywords={q}"
    if location:
        base_url += f"&location={location.replace(' ', '%20')}"

    driver = None
    try:
        log.info("Starting Chrome driver")
        driver = create_driver()
        log.info("Navigating to %s", base_url)
        driver.get(base_url)
        time.sleep(3)

        jobs = []
        # best-effort selectors
        cards = driver.find_elements(By.CSS_SELECTOR, "ul.jobs-search__results-list li") or driver.find_elements(By.CLASS_NAME, "base-card")
        for c in cards[:limit]:
            try:
                title = ""
                company = ""
                location_text = ""
                jobUrl = ""

                # try multiple selectors robustly
                try:
                    title = c.find_element(By.CSS_SELECTOR, ".base-search-card__title, .job-card-list__title, .job-card-search__title").text
                except:
                    pass
                try:
                    company = c.find_element(By.CSS_SELECTOR, ".base-search-card__subtitle, .result-card__subtitle, .job-card-container__company-name").text
                except:
                    pass
                try:
                    location_text = c.find_element(By.CSS_SELECTOR, ".job-search-card__location, .job-result-card__location").text
                except:
                    pass
                try:
                    jobUrl = c.find_element(By.CSS_SELECTOR, "a").get_attribute("href")
                except:
                    pass

                if not title and jobUrl:
                    # fallback: visit job page and read title
                    try:
                        driver.execute_script("window.open(arguments[0]);", jobUrl)
                        driver.switch_to.window(driver.window_handles[-1])
                        time.sleep(1)
                        try:
                            title = driver.find_element(By.CSS_SELECTOR, ".topcard__title, .job-top-card__title").text
                        except:
                            title = title
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    except Exception:
                        pass

                if title or jobUrl:
                    jobs.append({
                        "title": title or "",
                        "company": company or "",
                        "location": location_text or "",
                        "jobUrl": jobUrl or ""
                    })
            except Exception:
                continue

        return jsonify({"total": len(jobs), "jobs": jobs})

    except Exception as e:
        log.exception("Scrape error")
        return jsonify({"error": "scrape_failed", "detail": str(e)}), 500
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

@app.get("/")
def home():
    return {"status": "LinkedIn Scraper API live"}
