import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, abort, request
from flasgger import Swagger, swag_from # Import swag_from for cleaner docstring handling
import logging
from urllib.parse import unquote, quote
from flask_cors import CORS # Import CORS

# --- Basic Configuration ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# Flasgger Configuration for /docs/ endpoint
app.config['SWAGGER'] = {
    'title': 'Combined HQScraper API',
    'uiversion': 3,
    'specs_route': "/docs/",  # Serve Swagger UI at /docs/
    'description': 'All HQScraper APIs combined into one service with Swagger documentation.'
}
swagger = Swagger(app) # Initialize Flasgger

BASE_URL = "https://hqporn.xxx"
COMMON_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# --- Helper Functions (Scrapers) ---

# From input_file_0.py (stream_link_scraper_api.py)
def scrape_video_page_for_streams(video_page_url):
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    try:
        response = requests.get(video_page_url, headers=COMMON_HEADERS, timeout=20)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {video_page_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    stream_data = {
        "video_page_url": video_page_url,
        "main_video_src": None,
        "source_tags": [],
        "poster_image": None,
        "sprite_previews": []
    }
    video_tag = soup.find('video', id='video_html5_api')
    if not video_tag:
        player_div = soup.find('div', class_='b-video-player')
        if player_div:
            video_tag = player_div.find('video')
    if not video_tag:
        logger.warning(f"Video player tag not found on {video_page_url}.")
        return {"error": "Video player tag not found.", "details": stream_data}

    if video_tag.has_attr('src'):
        stream_data["main_video_src"] = video_tag['src']
        # Ensure the main_video_src is also in source_tags if not already listed by <source> tags
        if video_tag['src'] not in [s.get('src') for s in video_tag.find_all('source') if s.has_attr('src')]:
            stream_data["source_tags"].append({
                "src": video_tag['src'],
                "type": video_tag.get('type', 'video/mp4') # Guess type if not present
            })

    source_tags = video_tag.find_all('source')
    found_sources = set() # To track sources already added
    if stream_data["main_video_src"]:
        found_sources.add(stream_data["main_video_src"]) # Add src from main video tag if it exists

    for source_tag in source_tags:
        if source_tag.has_attr('src'):
            src_url = source_tag['src']
            if src_url not in found_sources: # Only add if not already captured
                stream_data["source_tags"].append({
                    "src": src_url,
                    "type": source_tag.get('type'),
                    "size": source_tag.get('size')
                })
                found_sources.add(src_url)
    
    # Further ensure uniqueness in the final list based on 'src'
    unique_sources_final = []
    seen_src_urls = set()
    for src_item in stream_data["source_tags"]:
        if src_item['src'] not in seen_src_urls:
            unique_sources_final.append(src_item)
            seen_src_urls.add(src_item['src'])
    stream_data["source_tags"] = unique_sources_final

    if video_tag.has_attr('poster'):
        stream_data["poster_image"] = video_tag['poster']
    if video_tag.has_attr('data-preview'):
        sprite_string = video_tag['data-preview']
        stream_data["sprite_previews"] = [sprite.strip() for sprite in sprite_string.split(',') if sprite.strip()]
    
    if not stream_data["source_tags"] and not stream_data["main_video_src"]: # Check after all processing
        logger.warning(f"No direct video src or source tags found for video on {video_page_url}.")
        stream_data["note"] = "No direct video <src> or <source> tags found."
    return stream_data

# From input_file_1.py (search_scraper_api.py)
def scrape_hqporn_search_page(search_content, page_number):
    safe_search_content = quote(search_content) # URL-encode the search query
    scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/search/{safe_search_content}/" # Page 1 might not have /1/
    
    logger.info(f"Attempting to scrape search results for '{search_content}' (page {page_number}): {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None # Indicates an error during the request

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')

    if not gallery_list_container:
        # Check for "no results" message
        no_results_message = soup.find('div', class_='b-catalog-info-descr')
        if no_results_message and "no results found" in no_results_message.get_text(strip=True).lower():
            logger.info(f"No search results found for '{search_content}' on {scrape_url}.")
        else:
            logger.warning(f"Gallery list container not found on {scrape_url}.")
        return [] # Return empty list if no container or no results message clearly indicates so

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on page {page_number} for search '{search_content}'.")
        return [] # Return empty list if container exists but has no items

    scraped_data = []
    for item_soup in items:
        data = {}
        link_tag = item_soup.find('a', class_='js-gallery-link')
        if link_tag:
            href = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            data['gallery_id'] = link_tag.get('data-gallery-id')
            data['thumb_id'] = link_tag.get('data-thumb-id')
            data['preview_video_url'] = link_tag.get('data-preview')
            data['title_attribute'] = link_tag.get('title') # Often same as the displayed title
        else:
            continue # Skip if no main link found

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data.get('title_attribute', 'N/A')
        
        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) # Prefer data-src for lazy loaded
        data['image_urls'] = image_urls

        duration_div = item_soup.find('div', class_='b-thumb-item__duration')
        duration_span = duration_div.find('span') if duration_div else None
        data['duration'] = duration_span.text.strip() if duration_span else None

        detail_div = item_soup.find('div', class_='b-thumb-item__detail')
        tags_list = []
        if detail_div:
            for tag_a in detail_div.find_all('a'): # Assuming tags are within <a> tags
                tag_name = tag_a.text.strip()
                tag_link_relative = tag_a.get('href')
                if tag_name and tag_link_relative:
                    tags_list.append({
                        'name': tag_name,
                        'link': f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    })
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

# From input_file_2.py (fresh_videos_scraper_api.py)
def scrape_hqporn_fresh_page(page_number):
    scrape_url = f"{BASE_URL}/fresh/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/fresh/"
    logger.info(f"Attempting to scrape (fresh/newest): {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}.")
        return [] 
    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on page {page_number} of /fresh/.")
        return []
    scraped_data = []
    # (Identical item parsing logic as scrape_hqporn_search_page, abstract or duplicate)
    for item_soup in items: # This block is very similar to other list scrapers
        data = {}
        link_tag = item_soup.find('a', class_='js-gallery-link')
        if link_tag:
            href = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            data['gallery_id'] = link_tag.get('data-gallery-id')
            data['thumb_id'] = link_tag.get('data-thumb-id')
            data['preview_video_url'] = link_tag.get('data-preview')
            data['title_attribute'] = link_tag.get('title')
        else: continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data.get('title_attribute', 'N/A')
        
        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag: image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls

        duration_div = item_soup.find('div', class_='b-thumb-item__duration')
        duration_span = duration_div.find('span') if duration_div else None
        data['duration'] = duration_span.text.strip() if duration_span else None

        detail_div = item_soup.find('div', class_='b-thumb-item__detail') # Contains tags
        tags_list = []
        if detail_div:
            for tag_a in detail_div.find_all('a'):
                tag_name = tag_a.text.strip()
                tag_link_relative = tag_a.get('href')
                if tag_name and tag_link_relative:
                    tags_list.append({
                        'name': tag_name,
                        'link': f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    })
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

# From input_file_3.py (best_videos_scraper_api.py)
def scrape_hqporn_best_page(page_number):
    scrape_url = f"{BASE_URL}/best/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/best/" # Page 1 might not have /1/
    logger.info(f"Attempting to scrape (best/top-rated): {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}.")
        return []
    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on page {page_number} of /best/.")
        return []
    scraped_data = []
    # (Identical item parsing logic, should be refactored ideally)
    for item_soup in items: # This block is very similar to other list scrapers
        data = {}
        link_tag = item_soup.find('a', class_='js-gallery-link')
        if link_tag:
            href = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            data['gallery_id'] = link_tag.get('data-gallery-id')
            data['thumb_id'] = link_tag.get('data-thumb-id')
            data['preview_video_url'] = link_tag.get('data-preview')
            data['title_attribute'] = link_tag.get('title')
        else: continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data.get('title_attribute', 'N/A')
        
        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag: image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls

        duration_div = item_soup.find('div', class_='b-thumb-item__duration')
        duration_span = duration_div.find('span') if duration_div else None
        data['duration'] = duration_span.text.strip() if duration_span else None

        detail_div = item_soup.find('div', class_='b-thumb-item__detail')
        tags_list = []
        if detail_div:
            for tag_a in detail_div.find_all('a'):
                tag_name = tag_a.text.strip()
                tag_link_relative = tag_a.get('href')
                if tag_name and tag_link_relative:
                    tags_list.append({
                        'name': tag_name,
                        'link': f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    })
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

# From input_file_4.py (channel_scraper_api.py)
def scrape_hqporn_channels_page(page_number):
    scrape_url = f"{BASE_URL}/channels/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/channels/"
    logger.info(f"Attempting to scrape channels from: {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list') # Corrected class from video to channel
    if not channel_list_container:
        logger.warning(f"Channel list container not found on {scrape_url}.")
        # Add a check if it found a video gallery list instead
        if soup.find('div', class_='js-gallery-list') and not soup.find('div', class_='js-channel-list'):
             logger.warning(f"Found a gallery list instead of channels on {scrape_url}.")
        return []
        
    items = channel_list_container.find_all('div', class_='b-thumb-item--cat') # class for channel items
    if not items:
        logger.info(f"No channel items found on page {page_number}.")
        return []
    scraped_data = []
    for item_soup in items:
        data = {}
        link_tag = item_soup.find('a', class_='js-channel-stats') # Specific class for channel links
        if link_tag:
            href_relative = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            data['channel_id'] = link_tag.get('data-channel-id')
            data['name'] = link_tag.get('title','').strip() # title attribute on <a> is usually the name
        else:
            continue

        # If title attribute was empty or missing, try to get from b-thumb-item__title
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span') # Text is often inside a span
            if title_span and title_span.get_text(strip=True):
                if not data.get('name'): # Only overwrite if not found from <a>'s title
                    data['name'] = title_span.get_text(strip=True)

        picture_tag = item_soup.find('picture') # General picture tag
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls
        
        # Only add if essential data like name and link is present
        if data.get('name') and data.get('link'):
            scraped_data.append(data)
        else:
            logger.warning(f"Skipping channel item due to missing name or link: {item_soup.prettify()}")

    return scraped_data

# From input_file_5.py (pornstar_scraper_api.py)
def scrape_hqporn_pornstars_page(page_number):
    scrape_url = f"{BASE_URL}/pornstars/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/pornstars/"
    logger.info(f"Attempting to scrape pornstars from: {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    # The container for pornstars has class 'js-pornstar-list' not 'js-channel-list'
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
    if not pornstar_list_container:
        logger.warning(f"Pornstar list container not found on {scrape_url}.")
        # Check if a video gallery list was found instead (common mistake if page structure changes)
        if soup.find('div', class_='js-gallery-list') and not soup.find('div', class_='js-pornstar-list'):
             logger.warning(f"Found a video/gallery list instead of pornstars on {scrape_url}.")
        return []
        
    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star') # Class for pornstar items
    if not items:
        logger.info(f"No pornstar items found on page {page_number}.")
        return []
    scraped_data = []
    for item_soup in items:
        data = {}
        link_tag = item_soup.find('a', class_='js-pornstar-stats') # Specific class for pornstar links
        if link_tag:
            href_relative = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            data['pornstar_id'] = link_tag.get('data-pornstar-id')
            data['name'] = link_tag.get('title', '').strip() # Name is usually in title attr
        else:
            continue

        # Fallback for name if not in <a> title attribute
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True) and not data.get('name'):
            data['name'] = title_div.get_text(strip=True)

        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls

        if data.get('name') and data.get('link'):
            scraped_data.append(data)
        else:
             logger.warning(f"Skipping pornstar item due to missing name or link.")
    return scraped_data

# From input_file_6.py (category_scraper_api.py)
def scrape_hqporn_categories_page(page_number):
    # URL was /categories/{page_number}, assuming /categories/{page_number}/ is more standard like others
    scrape_url = f"{BASE_URL}/categories/{page_number}/" 
    if page_number == 1:
        scrape_url = f"{BASE_URL}/categories/"
    logger.info(f"Attempting to scrape categories from: {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    # Correct class for category list is 'js-category-list'
    category_list_container = soup.find('div', id='galleries', class_='js-category-list') 
    if not category_list_container:
        logger.warning(f"Category list container not found on {scrape_url}.")
        # Check for common issue: finding video list instead of category list
        if soup.find('div', class_='js-gallery-list') and not soup.find('div', class_='js-category-list'):
             logger.warning(f"Found a video list instead of categories on {scrape_url}.")
        return []
        
    items = category_list_container.find_all('div', class_='b-thumb-item--cat') # Category items often use --cat or similar
    if not items:
        logger.info(f"No category items found on page {page_number}.")
        return []
    scraped_data = []
    for item_soup in items:
        data = {}
        link_tag = item_soup.find('a', class_='js-category-stats') # class specific to category links
        if link_tag:
            href_relative = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            data['category_id'] = link_tag.get('data-category-id')
            data['title'] = link_tag.get('title','').strip() # title attribute
        else:
            continue

        # Fallback if title not on <a>
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True):
            if not data.get('title'): # Only if not already set
                data['title'] = title_div.get_text(strip=True)

        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls
        
        if data.get('title') and data.get('link'): # Ensure basic info is present
            scraped_data.append(data)
        else:
            logger.warning(f"Skipping category item due to missing title or link.")
    return scraped_data

# From input_file_7.py (scraper_api.py), renamed to scrape_hqporn_trend_page
def scrape_hqporn_trend_page(page_number):
    # The original URL for trend was /trend/{page_number} (no trailing slash)
    # but other scrapers use trailing slashes for paginated content. Sticking to pattern.
    scrape_url = f"{BASE_URL}/trend/{page_number}/"
    if page_number == 1 : # Page 1 url does not have number. Eg : /trend/
        scrape_url = f"{BASE_URL}/trend/"
    
    logger.info(f"Attempting to scrape (trend): {scrape_url}")
    try:
        response = requests.get(scrape_url, headers=COMMON_HEADERS, timeout=15)
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None # Indicates failure to fetch

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')

    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}.")
        return [] # Return empty list if container not found

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on page {page_number} of /trend/.")
        return [] # Return empty list if no items found

    scraped_data = []
    # (Identical item parsing logic, should be refactored ideally)
    for item_soup in items: # This block is very similar to other list scrapers
        data = {}
        link_tag = item_soup.find('a', class_='js-gallery-link')
        if link_tag:
            href = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            data['gallery_id'] = link_tag.get('data-gallery-id')
            data['thumb_id'] = link_tag.get('data-thumb-id')
            data['preview_video_url'] = link_tag.get('data-preview')
            data['title_attribute'] = link_tag.get('title') # This usually holds the title
        else:
            continue # If no link tag, skip this item

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data.get('title_attribute', 'N/A')
        
        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) # data-src for lazy loaded
        data['image_urls'] = image_urls

        duration_div = item_soup.find('div', class_='b-thumb-item__duration')
        duration_span = duration_div.find('span') if duration_div else None
        data['duration'] = duration_span.text.strip() if duration_span else None

        detail_div = item_soup.find('div', class_='b-thumb-item__detail') # Contains tags
        tags_list = []
        if detail_div:
            for tag_a in detail_div.find_all('a'): # Assuming tags are <a> tags within this div
                tag_name = tag_a.text.strip()
                tag_link_relative = tag_a.get('href')
                if tag_name and tag_link_relative:
                    tags_list.append({
                        'name': tag_name,
                        'link': f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    })
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data


# --- API Endpoints ---

@app.route('/api/stream/<path:video_page_link>', methods=['GET'])
@swag_from({ # Using dict for swag_from for clarity
    'tags': ['Streams'],
    'parameters': [
        {
            'name': 'video_page_link',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'The full URL of the video page to scrape (e.g., https://hqporn.xxx/example_video.html).'
        }
    ],
    'responses': {
        200: {
            'description': 'Successfully scraped stream data.',
            'schema': { # More detailed schema
                'type': 'object',
                'properties': {
                    'video_page_url': {'type': 'string', 'format': 'url'},
                    'main_video_src': {'type': 'string', 'format': 'url', 'nullable': True},
                    'source_tags': {
                        'type': 'array',
                        'items': {
                            'type': 'object',
                            'properties': {
                                'src': {'type': 'string', 'format': 'url'},
                                'type': {'type': 'string', 'nullable': True},
                                'size': {'type': 'string', 'nullable': True} # Could be integer too
                            }
                        }
                    },
                    'poster_image': {'type': 'string', 'format': 'url', 'nullable': True},
                    'sprite_previews': {'type': 'array', 'items': {'type': 'string', 'format': 'url'}},
                    'note': {'type': 'string', 'nullable': True}
                }
            }
        },
        400: {'description': 'Invalid video page link format. Must be a full URL.'},
        404: {'description': 'Video player tag not found or content parsing issue.'},
        500: {'description': 'Failed to scrape the video page (e.g., website down, content unavailable).'}
    }
})
def get_stream_links(video_page_link):
    if not video_page_link.startswith("http"): # Basic validation
        return jsonify({"error": f"Invalid video_page_link. It must be a full URL. Received: {video_page_link}"}), 400
    
    logger.info(f"Received request for video page link: {video_page_link}")
    data = scrape_video_page_for_streams(video_page_link)
    
    if data is None: # Scraper indicated a fetch error
        abort(500, description="Failed to scrape the video page. The website might be down or content is not available.")
    if "error" in data and data.get("error") == "Video player tag not found.": # Specific error from scraper
        return jsonify(data), 404 # Return 404 for "not found" type errors
    
    return jsonify(data)

@app.route('/api/search/<string:search_content>/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Search'],
    'parameters': [
        {
            'name': 'search_content',
            'in': 'path',
            'type': 'string',
            'required': True,
            'description': 'The search query (URL-encoded if it contains special characters).'
        },
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number of the search results (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of search results or an empty list if no results found.',
            'schema': {
                'type': 'array',
                'items': { # Define a generic item structure, actual structure depends on scraper
                    'type': 'object',
                     'properties': {
                        'link': {'type': 'string', 'format': 'url'},
                        'title': {'type': 'string'},
                        'image_urls': {'type': 'object'},
                        'duration': {'type': 'string', 'nullable': True},
                        'tags': {'type': 'array', 'items': {'type': 'object'}}
                    }
                }
            }
        },
        400: {'description': 'Invalid input (e.g., empty search content, non-positive page number).'},
        500: {'description': 'Failed to scrape the search results page (server-side issue or website unavailable).'}
    }
})
def get_search_results_page(search_content, page_number):
    # The search_content comes URL-decoded by Flask. The scraper will re-encode it.
    if not search_content.strip(): # Check if search content is empty or just whitespace
        return jsonify({"error": "Search content cannot be empty."}), 400
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
        
    data = scrape_hqporn_search_page(search_content, page_number)
    if data is None: # Indicates a failure in the scraper function (e.g., request error)
        abort(500, description="Failed to scrape the search results page.")
    # If data is an empty list, it means no results were found or page was empty, which is a valid 200 response.
    return jsonify(data)

@app.route('/api/fresh/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Videos'],
    'parameters': [
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number for fresh videos (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of fresh videos or an empty list if page has no videos.',
            'schema': {
                'type': 'array',
                'items': { # Define item structure, mirrors search result item typically
                    'type': 'object',
                     'properties': {
                        'link': {'type': 'string', 'format': 'url'},
                        'title': {'type': 'string'},
                        'image_urls': {'type': 'object'},
                        'duration': {'type': 'string', 'nullable': True},
                        'tags': {'type': 'array', 'items': {'type': 'object'}}
                    }
                }
            }
        },
        400: {'description': 'Invalid page number (must be positive).'},
        500: {'description': 'Failed to scrape the fresh videos page.'}
    }
})
def get_fresh_page(page_number):
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
    data = scrape_hqporn_fresh_page(page_number)
    if data is None: # Scraper failed
        abort(500, description="Failed to scrape the fresh videos page.")
    return jsonify(data) # Empty list is a valid response for an empty page

@app.route('/api/best/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Videos'],
    'parameters': [
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number for best-rated videos (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of best-rated videos or an empty list.',
             'schema': {
                'type': 'array',
                'items': { 
                    'type': 'object',
                     'properties': {
                        'link': {'type': 'string', 'format': 'url'},
                        'title': {'type': 'string'},
                        'image_urls': {'type': 'object'},
                        'duration': {'type': 'string', 'nullable': True},
                        'tags': {'type': 'array', 'items': {'type': 'object'}}
                    }
                }
            }
        },
        400: {'description': 'Invalid page number (must be positive).'},
        500: {'description': 'Failed to scrape the best-rated videos page.'}
    }
})
def get_best_rated_page(page_number):
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
    data = scrape_hqporn_best_page(page_number)
    if data is None:
        abort(500, description="Failed to scrape the best-rated videos page.")
    return jsonify(data)

@app.route('/api/channels/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Channels'],
    'parameters': [
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number for channels (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of channels or an empty list.',
            'schema': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                       'link': {'type': 'string', 'format': 'url'},
                       'name': {'type': 'string'},
                       'channel_id': {'type': 'string', 'nullable': True},
                       'image_urls': {'type': 'object'}
                    }
                }
            }
        },
        400: {'description': 'Invalid page number (must be positive).'},
        500: {'description': 'Failed to scrape the channels page.'}
    }
})
def get_channels_page(page_number):
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
    data = scrape_hqporn_channels_page(page_number)
    if data is None:
        abort(500, description="Failed to scrape the channels page.")
    return jsonify(data)

@app.route('/api/pornstars/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Pornstars'],
    'parameters': [
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number for pornstars (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of pornstars or an empty list.',
            'schema': {
                'type': 'array',
                'items': {
                    'type': 'object',
                     'properties': {
                       'link': {'type': 'string', 'format': 'url'},
                       'name': {'type': 'string'},
                       'pornstar_id': {'type': 'string', 'nullable': True},
                       'image_urls': {'type': 'object'}
                    }
                }
            }
        },
        400: {'description': 'Invalid page number (must be positive).'},
        500: {'description': 'Failed to scrape the pornstars page.'}
    }
})
def get_pornstars_page(page_number):
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
    data = scrape_hqporn_pornstars_page(page_number)
    if data is None:
        abort(500, description="Failed to scrape the pornstars page.")
    return jsonify(data)

@app.route('/api/categories/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Categories'],
    'parameters': [
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number for categories (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of categories or an empty list.',
             'schema': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                       'link': {'type': 'string', 'format': 'url'},
                       'title': {'type': 'string'}, # Renamed 'name' to 'title' to match scraper
                       'category_id': {'type': 'string', 'nullable': True},
                       'image_urls': {'type': 'object'}
                    }
                }
            }
        },
        400: {'description': 'Invalid page number (must be positive).'},
        500: {'description': 'Failed to scrape the categories page.'}
    }
})
def get_categories_page(page_number):
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
    data = scrape_hqporn_categories_page(page_number)
    if data is None:
        abort(500, description="Failed to scrape the categories page.")
    return jsonify(data)

@app.route('/api/trend/<int:page_number>', methods=['GET'])
@swag_from({
    'tags': ['Videos'],
    'parameters': [
        {
            'name': 'page_number',
            'in': 'path',
            'type': 'integer',
            'required': True,
            'minimum': 1,
            'description': 'The page number for trending videos (must be 1 or greater).'
        }
    ],
    'responses': {
        200: {
            'description': 'List of trending videos or an empty list.',
            'schema': {
                'type': 'array',
                'items': {
                    'type': 'object',
                     'properties': {
                        'link': {'type': 'string', 'format': 'url'},
                        'title': {'type': 'string'},
                        'image_urls': {'type': 'object'},
                        'duration': {'type': 'string', 'nullable': True},
                        'tags': {'type': 'array', 'items': {'type': 'object'}}
                    }
                }
            }
        },
        400: {'description': 'Invalid page number (must be positive).'},
        500: {'description': 'Failed to scrape the trending videos page.'}
    }
})
def get_trend_page(page_number):
    if page_number <= 0:
        return jsonify({"error": "Page number must be positive."}), 400
    data = scrape_hqporn_trend_page(page_number) # Use the renamed helper
    if data is None:
        abort(500, description="Failed to scrape the trending videos page.")
    return jsonify(data)

# --- Main Application Runner ---
if __name__ == '__main__':
    # For production, use a WSGI server (e.g., Gunicorn)
    # Example: gunicorn -w 4 -b 0.0.0.0:5000 input_file_0:app 
    # (replace 'input_file_0' with the actual filename)
    app.run(debug=True, host='0.0.0.0', port=5000)
