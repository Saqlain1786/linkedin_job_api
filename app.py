import os
import time
import logging
from flask import Flask, request, jsonify
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("linkedin-scraper")

app = Flask(__name__)

# A realistic user-agent string (Chrome on Windows) — rotate if you later need.
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0.0.0 Safari/537.36")

def create_driver(user_agent=DEFAULT_UA):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(f'--user-agent={user_agent}')
    chrome_options.add_argument("--disable-gpu")
    # Avoid some automation flags
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)

    chromedriver_path = ChromeDriverManager().install()
    service = Service(executable_path=chromedriver_path)
    driver = webdriver.Chrome(service=service, options=chrome_options)

    # Use CDP to inject stealth tweaks for each new document
    try:
        # 1) Hide navigator.webdriver
        script = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": script})

        # 2) Mock plugins/languages
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});"})
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4]});"})
        # 3) Override userAgent via Network (ensures requests show the UA used)
        driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": user_agent})
    except Exception:
        # CDP not critical — proceed anyway
        pass

    driver.set_page_load_timeout(30)
    return driver

def scroll_container(driver, container_css, times=6, pause=0.8):
    """Scroll container element to force lazy-loading of jobs."""
    try:
        for i in range(times):
            driver.execute_script(
                "const el = document.querySelector(arguments[0]); if(el){ el.scrollTop = el.scrollTop + el.clientHeight; }", 
                container_css
            )
            time.sleep(pause)
    except Exception:
        pass

@app.get("/")
def home():
    return {"status": "LinkedIn Scraper API live"}

@app.get("/search")
def search():
    """
    Example:
    /search?keyword=service%20desk&location=United%20States&limit=100&require_remote=true
    """
    keyword = request.args.get("keyword", "service desk")
    location = request.args.get("location", "")
    try:
        limit = min(int(request.args.get("limit", 100)), 200)
    except:
        limit = 100
    require_remote = request.args.get("require_remote", "false").lower() == "true"
    require_contract = request.args.get("require_contract", "false").lower() == "true"

    q = keyword.replace(" ", "%20")
    url = f"https://www.linkedin.com/jobs/search/?keywords={q}"
    if location:
        url += f"&location={location.replace(' ', '%20')}"

    driver = None
    try:
        log.info("Creating driver and navigating to search URL: %s", url)
        driver = create_driver()
        driver.get(url)

        # Wait for the expected job list container
        wait = WebDriverWait(driver, 15)
        try:
            # primary LinkedIn job list container
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.jobs-search__results-list")))
            container_selector = "ul.jobs-search__results-list"
        except Exception:
            # fallback to another common container
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".jobs-search-results__list")))
                container_selector = ".jobs-search-results__list"
            except Exception:
                # fallback to base-card nodes
                container_selector = None

        # If we found a container, scroll it to load lazy items
        if container_selector:
            scroll_container(driver, container_selector, times=8, pause=0.7)
            time.sleep(1.2)
        else:
            # attempt a generic page scroll
            for _ in range(3):
                driver.execute_script("window.scrollBy(0, window.innerHeight);")
                time.sleep(0.7)

        # Try to collect job elements robustly
        job_nodes = driver.find_elements(By.CSS_SELECTOR, "ul.jobs-search__results-list li")
        if not job_nodes:
            job_nodes = driver.find_elements(By.CSS_SELECTOR, "li.jobs-search-results__list-item, .base-card")

        jobs = []
        for node in job_nodes[:limit]:
            try:
                title = ""
                company = ""
                loc_text = ""
                job_url = ""

                try:
                    title = node.find_element(By.CSS_SELECTOR, ".base-search-card__title, .job-card-list__title").text.strip()
                except:
                    pass
                try:
                    company = node.find_element(By.CSS_SELECTOR, ".base-search-card__subtitle, .job-card-container__company-name").text.strip()
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

        out = {
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
        log.info("Returning %d jobs (fetched=%d)", out["returned"], out["totalFetched"])
        return jsonify(out)

    except Exception as e:
        log.exception("Runtime error in /search")
        return jsonify({"error": "runtime_error", "detail": str(e)}), 500

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
