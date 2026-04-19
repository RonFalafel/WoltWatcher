import logging
import urllib.parse
import re
from playwright.async_api import async_playwright, TimeoutError

def resolve_wolt_url(url: str) -> str:
    """Clean the URL and use it directly."""
    try:
        url = urllib.parse.unquote(url).strip()
        url = ''.join(c for c in url if c.isprintable() and not c.isspace())
        url = url.split('?')[0]
        
        # Force English UI so our text scraping logic doesn't break on localized links
        url = re.sub(r'wolt\.com/[a-z]{2}/', 'wolt.com/en/', url)
        
        return url
    except Exception as e:
        logging.error(f'Error resolving URL {url}: {e}')
        return url

async def check_wolt_page(url: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_selector("h1", timeout=15000)
            await page.wait_for_timeout(10000)
            
            body_locator = page.locator("body")
            page_text = (await body_locator.text_content() or "").lower()
            
            h1_locator = page.locator("h1")
            h1_text = (await h1_locator.text_content() or "").strip()

            # 1. Anti-bot protection check
            cloudflare_phrases = [
                "just a moment",
                "attention required",
                "verify you are human",
                "cloudflare"
            ]
            if any(phrase in page_text for phrase in cloudflare_phrases):
                logging.error(f"[!] Blocked by Cloudflare: {url}")
                await browser.close()
                return False, "Unknown (Blocked)", url

            # 2. Check offline phrases
            offline_phrases = [
                "offline",
                "not accepting orders",
                "currently not accepting orders",
                "opens at",
                "opens tomorrow",
                "opens on",
                "opens today",
                "opens ",
                "temporarily closed",
                "schedule order",
                # Hebrew translations in case Wolt overrides the /en/ locale
                "סגור",
                "לא מקבלים הזמנות",
                "כרגע לא מקבלים",
                "נפתח ב",
                "נפתח מחר",
                "נפתח היום",
                "נפתח ביום",
                "הזמנה עתידית"
            ]

            is_closed = any(phrase in page_text for phrase in offline_phrases)
            final_url = page.url.split('?')[0]

            await browser.close()
            return not is_closed, h1_text, final_url

        except TimeoutError:
            logging.error(f"[!] Timeout waiting for page to load or H1 not found: {url}")
            await browser.close()
            return False, "Unknown (Timeout)", url
        except Exception as e:
            logging.error(f"[!] Playwright error: {e}")
            await browser.close()
            return False, "Unknown (Error)", url

async def get_restaurant_status(slug_or_url: str):
    online, name, url = await check_wolt_page(slug_or_url)
    return (online, name, url)

async def find_restaurant(slug_or_url, filters, force_exact_match=False):
    online, name, final_url = await check_wolt_page(slug_or_url)

    if name.startswith("Unknown"):
        return [{'error': '404', 'slug': slug_or_url}]

    return [{
        'online' : online,
        'slug' : final_url,
        'address' : 'Playwright verified',
        'name' : name,
        'url' : final_url
    }]
