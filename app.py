import os, time, logging
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("linkedin-scraper")

app = Flask(__name__)

def create_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    # Use webdriver-manager to obtain a compatible chromedriver binary
    chromedriver_path = ChromeDriverManager(log_level=0).install()
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)
    driver.set_page_load_timeout(30)
    return driver

@app.get("/")
def home():
    return {"status": "LinkedIn Scraper API live"}

@app.get("/search")
def search():
    """
    GET /search?keyword=service%20desk&location=United%20States&limit=100&require_remote=true&require_contract=false
    Returns: JSON { total: N, jobs: [...] }
    """
    keyword = request.args.get("keyword", "service desk")
    location = request.args.get("location", "")
    limit = min(int(request.args.get("limit", 100)), 200)
    require_remote = request.args.get("require_remote", "false").lower() == "true"
    require_contract = request.args.get("require_contract", "false").lower() == "true"

    q = keyword.replace(" ", "%20")
    base_url = f"https://www.linkedin.com/jobs/search/?keywords={q}"
    if location:
        base_url += f"&location={location.replace(' ', '%20')}"

    driver = None
    try:
        log.info("Creating driver and navigating to search URL")
        driver = create_driver()
        driver.get(base_url)
        time.sleep(3)  # allow page to render

        # try multiple reasonable selectors; linkedin DOM changes frequently so we fall back gracefully
        job_nodes = driver.find_elements(By.CSS_SELECTOR, "ul.jobs-search__results-list li")
        if not job_nodes:
            job_nodes = driver.find_elements(By.CSS_SELECTOR, ".base-card")

        jobs = []
        for node in job_nodes[:limit]:
            try:
                title = ""
                company = ""
                loc_text = ""
                job_url = ""

                # robust attempts to extract text using multiple selectors
                try:
                    title = node.find_element(By.CSS_SELECTOR, ".base-search-card__title, .job-card-list__title, .job-card-search__title").text.strip()
                except:
                    pass
                try:
                    company = node.find_element(By.CSS_SELECTOR, ".base-search-card__subtitle, .result-card__subtitle, .job-card-container__company-name").text.strip()
                except:
                    pass
                try:
                    loc_text = node.find_element(By.CSS_SELECTOR, ".job-search-card__location, .job-result-card__location").text.strip()
                except:
                    pass
                try:
                    job_url = node.find_element(By.CSS_SELECTOR, "a").get_attribute("href") or ""
                except:
                    pass

                # If title missing but URL present, optionally visit the job page to extract title (skipped to conserve memory/time)
                # Apply simple remote / contract heuristics
                hay = " ".join([title, company, loc_text]).lower()
                is_remote = "remote" in hay or "work from home" in hay or "wfh" in hay
                is_contract = any(tok in hay for tok in ["contract", "contractor", "temp", "temporary", "freelance"])

                if require_remote and not is_remote:
                    continue
                if require_contract and not is_contract:
                    continue

                jobs.append({
                    "jobId": (job_url.split("/")[-1] if job_url else f"no-id-{len(jobs)+1}"),
                    "position": title,
                    "company": company,
                    "location": loc_text,
                    "date": "",
                    "salary": "",
                    "jobUrl": job_url,
                    "companyUrl": "",
                    "companyLogo": "",
                    "descriptionSnippet": "",
                    "isRemote": is_remote,
                    "isContract": is_contract
                })
            except Exception:
                continue

        output = {
            "totalFetched": len(job_nodes),
            "totalMatchedAfterFilters": len(jobs),
            "returned": len(jobs),
            "paramsUsed": {
                "keyword": keyword,
                "location": location,
                "limit": limit,
                "requireRemote": require_remote,
                "requireContract": require_contract
            },
            "jobs": jobs
        }
        return jsonify(output)

    except Exception as e:
        log.exception("Runtime error in /search")
        return jsonify({"error": "runtime_error", "detail": str(e)}), 500
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

if __name__ == "__main__":
    # fallback only for local run
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
