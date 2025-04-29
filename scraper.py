import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import concurrent.futures
import logging

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def clean_text(text):
    return ' '.join(text.strip().split())

TARGET_TAGS = [
    "p", "h1", "h2", "h3", "h4", "h5", "h6",
    "span", "div", "strong", "b", "em", "i",
    "a", "li", "label", "blockquote", "pre", "code"
]

def extract_content_from_tags(soup):
    seen = set()
    lines = []

    for element in soup.find_all(TARGET_TAGS):
        text = clean_text(element.get_text())
        if (
            text and 
            len(text) > 30 and
            len(text) < 1000 and
            text.lower() not in seen and
            not any(bad in text.lower() for bad in ["cookies", "login", "terms", "privacy", "accept", "menu", "subscribe", "contact", "book", "footer"])
        ):
            lines.append(text)
            seen.add(text.lower())

    return lines

def scrape_website(url, depth=0, max_depth=2, visited=None, max_links=10, timeout=5):
    if visited is None:
        visited = set()

    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        logger.error(f"Invalid URL: {url}")
        return []

    if url in visited or depth > max_depth:
        return []

    visited.add(url)
    all_text = []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        all_text.extend(extract_content_from_tags(soup))

        base_url = "{0.scheme}://{0.netloc}".format(urlparse(url))
        links = [urljoin(base_url, a["href"]) for a in soup.find_all("a", href=True)]
        links = links[:max_links]

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {
                executor.submit(scrape_website, link, depth + 1, max_depth, visited, max_links // 2, timeout): link 
                for link in links if base_url in link and link not in visited
            }

            for future in concurrent.futures.as_completed(future_to_url, timeout=30):
                try:
                    nested_text = future.result()
                    all_text.extend(nested_text)
                except Exception as exc:
                    logger.warning(f'Link generated an exception: {exc}')

        return all_text

    except requests.exceptions.RequestException as e:
        logger.error(f"Error scraping {url}: {str(e)}")
        return []

def save_content_to_txt(lines, filename="scraped_content.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n\n")
