# scraper_api.py

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, abort
from flask_restx import Api, Resource, fields
from flask_cors import CORS
import logging
from urllib.parse import quote, unquote
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS to allow requests from any origin

# Initialize Flask-RESTX for Swagger documentation
api = Api(
    app,
    version='1.0',
    title='HQ Porn Scraper API',
    description='A unified API for scraping fresh, best, trending videos, pornstars, channels, categories, search results, and stream links from hqporn.xxx',
    doc='/api/docs/'
)

BASE_URL = "https://hqporn.xxx"

# Define namespaces for better organization in Swagger
ns_fresh = api.namespace('fresh', description='Operations related to fresh videos')
ns_best = api.namespace('best', description='Operations related to best-rated videos')
ns_trend = api.namespace('trend', description='Operations related to trending videos')
ns_pornstars = api.namespace('pornstars', description='Operations related to pornstars')
ns_channels = api.namespace('channels', description='Operations related to channels')
ns_categories = api.namespace('categories', description='Operations related to categories')
ns_search = api.namespace('search', description='Operations related to search results')
ns_stream = api.namespace('stream', description='Operations related to video stream links')

# Define data models for Swagger documentation
video_model = api.model('Video', {
    'link': fields.String(description='Video page URL'),
    'gallery_id': fields.String(description='Gallery ID'),
    'thumb_id': fields.String(description='Thumbnail ID'),
    'preview_video_url': fields.String(description='Preview video URL'),
    'title_attribute': fields.String(description='Title from link attribute'),
    'title': fields.String(description='Video title'),
    'image_urls': fields.Nested(api.model('ImageURLs', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    })),
    'duration': fields.String(description='Video duration'),
    'tags': fields.List(fields.Nested(api.model('Tag', {
        'name': fields.String(description='Tag name'),
        'link': fields.String(description='Tag URL')
    })))
})

pornstar_model = api.model('Pornstar', {
    'link': fields.String(description='Pornstar page URL'),
    'pornstar_id': fields.String(description='Pornstar ID'),
    'name': fields.String(description='Pornstar name'),
    'image_urls': fields.Nested(api.model('ImageURLs', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

channel_model = api.model('Channel', {
    'link': fields.String(description='Channel page URL'),
    'channel_id': fields.String(description='Channel ID'),
    'name': fields.String(description='Channel name'),
    'image_urls': fields.Nested(api.model('ImageURLs', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

category_model = api.model('Category', {
    'link': fields.String(description='Category page URL'),
    'category_id': fields.String(description='Category ID'),
    'title': fields.String(description='Category title'),
    'image_urls': fields.Nested(api.model('ImageURLs', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

stream_model = api.model('Stream', {
    'video_page_url': fields.String(description='Video page URL'),
    'main_video_src': fields.String(description='Main video source URL'),
    'source_tags': fields.List(fields.Nested(api.model('SourceTag', {
        'src': fields.String(description='Source URL'),
        'type': fields.String(description='Source type'),
        'size': fields.String(description='Source size')
    }))),
    'poster_image': fields.String(description='Poster image URL'),
    'sprite_previews': fields.List(fields.String, description='Sprite preview URLs'),
    'error': fields.String(description='Error message, if any'),
    'note': fields.String(description='Additional notes, if any')
})

def scrape_hqporn_fresh_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/fresh/
    """
    scrape_url = f"{BASE_URL}/fresh/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/fresh/"

    logger.info(f"Attempting to scrape (fresh/newest): {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}. It might be an empty page or end of pagination.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    
    if not items:
        logger.info(f"No items found on page {page_number} of /fresh/. This could be the end of pagination.")
        return []

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
            data['title_attribute'] = link_tag.get('title')
        else:
            logger.warning("Found an item with no js-gallery-link.")
            continue

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
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        
        scraped_data.append(data)

    return scraped_data

def scrape_hqporn_best_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/best/
    """
    scrape_url = f"{BASE_URL}/best/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/best/"

    logger.info(f"Attempting to scrape (best/top-rated): {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}. It might be an empty page or end of pagination.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    
    if not items:
        logger.info(f"No items found on page {page_number} of /best/. This could be the end of pagination.")
        return []

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
            data['title_attribute'] = link_tag.get('title')
        else:
            logger.warning("Found an item with no js-gallery-link.")
            continue

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
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        
        scraped_data.append(data)

    return scraped_data

def scrape_hqporn_trend_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/trend/
    """
    scrape_url = f"{BASE_URL}/trend/{page_number}"

    logger.info(f"Attempting to scrape (trending): {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}. It might be an empty page or end of pagination.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    
    if not items:
        logger.info(f"No items found on page {page_number} of /trend/. This could be the end of pagination.")
        return []

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
            data['title_attribute'] = link_tag.get('title')
        else:
            logger.warning("Found an item with no js-gallery-link.")
            continue

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
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        
        scraped_data.append(data)

    return scraped_data

def scrape_hqporn_pornstars_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/pornstars/
    """
    scrape_url = f"{BASE_URL}/pornstars/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/pornstars/"

    logger.info(f"Attempting to scrape pornstars from: {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
    if not pornstar_list_container:
        logger.warning(f"Pornstar list container not found on {scrape_url}. It might be an empty page or end of pagination.")
        if soup.find('div', class_='js-gallery-list') and not soup.find('div', class_='js-pornstar-list'):
            logger.warning(f"Found a video/gallery list instead of pornstars on {scrape_url}. Likely end of pornstar pagination.")
            return []
        return []

    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')
    
    if not items:
        logger.info(f"No pornstar items found on page {page_number}. This could be the end of pagination.")
        return []

    scraped_data = []

    for item_soup in items:
        data = {}

        link_tag = item_soup.find('a', class_='js-pornstar-stats')
        if link_tag:
            href_relative = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            data['pornstar_id'] = link_tag.get('data-pornstar-id')
            data['name'] = link_tag.get('title', '').strip()
        else:
            logger.warning("Found a pornstar item with no js-pornstar-stats link.")
            continue

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
            logger.warning(f"Skipping pornstar item due to missing name or link: {item_soup.prettify()}")

    return scraped_data

def scrape_hqporn_channels_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/channels/
    """
    scrape_url = f"{BASE_URL}/channels/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/channels/"

    logger.info(f"Attempting to scrape channels from: {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')
    if not channel_list_container:
        logger.warning(f"Channel list container not found on {scrape_url}. It might be an empty page or end of pagination.")
        if soup.find('div', class_='js-gallery-list') and not soup.find('div', class_='js-channel-list'):
            logger.warning(f"Found a gallery list instead of channels on {scrape_url}. Likely end of channel pagination.")
            return []
        return []

    items = channel_list_container.find_all('div', class_='b-thumb-item--cat')
    
    if not items:
        logger.info(f"No channel items found on page {page_number}. This could be the end of pagination for channels.")
        return []

    scraped_data = []

    for item_soup in items:
        data = {}

        link_tag = item_soup.find('a', class_='js-channel-stats')
        if link_tag:
            href_relative = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            data['channel_id'] = link_tag.get('data-channel-id')
            data['name'] = link_tag.get('title', '').strip()
        else:
            logger.warning("Found a channel item with no js-channel-stats link.")
            continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span')
            if title_span and title_span.get_text(strip=True):
                data['name'] = title_span.get_text(strip=True)

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
            logger.warning(f"Skipping channel item due to missing name or link: {item_soup.prettify()}")

    return scraped_data

def scrape_hqporn_categories_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/categories/
    """
    scrape_url = f"{BASE_URL}/categories/{page_number}"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/categories/"

    logger.info(f"Attempting to scrape categories from: {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    category_list_container = soup.find('div', id='galleries', class_='js-category-list')
    if not category_list_container:
        logger.warning(f"Category list container not found on {scrape_url}. It might be an empty page or end of pagination.")
        if soup.find('div', class_='js-gallery-list') and not soup.find('div', class_='js-category-list'):
            logger.warning(f"Found a video list instead of categories on {scrape_url}. Likely end of category pagination.")
            return []
        return []

    items = category_list_container.find_all('div', class_='b-thumb-item--cat')
    
    if not items:
        logger.info(f"No category items found on page {page_number}. This could be the end of pagination for categories.")
        return []

    scraped_data = []

    for item_soup in items:
        data = {}

        link_tag = item_soup.find('a', class_='js-category-stats')
        if link_tag:
            href_relative = link_tag.get('href')
            data['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            data['category_id'] = link_tag.get('data-category-id')
            data['title'] = link_tag.get('title', '').strip()
        else:
            logger.warning("Found a category item with no js-category-stats link.")
            continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True):
            title_from_div = title_div.get_text(strip=True)
            if not data.get('title'):
                data['title'] = title_from_div

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
        
        if data.get('title') and data.get('link'):
            scraped_data.append(data)
        else:
            logger.warning(f"Skipping category item due to missing title or link: {item_soup.prettify()}")

    return scraped_data

def scrape_hqporn_search_page(search_content, page_number):
    """
    Scrapes a specific page number from hqporn.xxx/search/{search_content}/
    """
    safe_search_content = quote(search_content)
    scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/search/{safe_search_content}/"

    logger.info(f"Attempting to scrape search results for '{search_content}' (page {page_number}): {scrape_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        no_results_message = soup.find('div', class_='b-catalog-info-descr')
        if no_results_message and "no results found" in no_results_message.get_text(strip=True).lower():
            logger.info(f"No search results found for '{search_content}' on {scrape_url}.")
        else:
            logger.warning(f"Gallery list container not found on {scrape_url}. It might be an empty page or different layout.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    
    if not items:
        logger.info(f"No items found on page {page_number} for search '{search_content}'. End of pagination or no results.")
        return []

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
            data['title_attribute'] = link_tag.get('title')
        else:
            logger.warning("Found an item with no js-gallery-link.")
            continue

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
                image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        
        scraped_data.append(data)

    return scraped_data

def scrape_video_page_for_streams(video_page_url):
    """
    Scrapes a specific video page URL for streaming links, poster, and sprites.
    """
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        response = requests.get(video_page_url, headers=headers, timeout=20)
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
        if video_tag['src'] not in [s.get('src') for s in video_tag.find_all('source') if s.has_attr('src')]:
            stream_data["source_tags"].append({
                "src": video_tag['src'],
                "type": video_tag.get('type', 'video/mp4')
            })

    source_tags = video_tag.find_all('source')
    found_sources = set()
    if stream_data["main_video_src"]:
        found_sources.add(stream_data["main_video_src"])

    for source_tag in source_tags:
        if source_tag.has_attr('src'):
            src_url = source_tag['src']
            if src_url not in found_sources:
                stream_data["source_tags"].append({
                    "src": src_url,
                    "type": source_tag.get('type'),
                    "size": source_tag.get('size')
                })
                found_sources.add(src_url)
    
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
    
    if not stream_data["source_tags"] and not stream_data["main_video_src"]:
        logger.warning(f"No direct video src or source tags found for video on {video_page_url}.")
        stream_data["note"] = "No direct video <src> or <source> tags found. Video content might be loaded via JavaScript."

    return stream_data

# Define API endpoints using Flask-RESTX
@ns_fresh.route('/<int:page_number>')
class FreshVideos(Resource):
    @api.doc(description='Get fresh videos for a specific page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_fresh_page(page_number)
        if data is None:
            abort(500, description="Failed to scrape the page. The website might be down or content is not available.")
        return jsonify(data)

@ns_best.route('/<int:page_number>')
class BestVideos(Resource):
    @api.doc(description='Get best-rated videos for a specific page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_best_page(page_number)
        if data is None:
            abort(500, description="Failed to scrape the page. The website might be down or content is not available.")
        return jsonify(data)

@ns_trend.route('/<int:page_number>')
class TrendVideos(Resource):
    @api.doc(description='Get trending videos for a specific page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_trend_page(page_number)
        if data is None:
            abort(500, description="Failed to scrape the page. The website might be down or content is not available.")
        return jsonify(data)

@ns_pornstars.route('/<int:page_number>')
class Pornstars(Resource):
    @api.doc(description='Get pornstars for a specific page number')
    @api.response(200, 'Success', [pornstar_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_pornstars_page(page_number)
        if data is None:
            abort(500, description="Failed to scrape the pornstars page. The website might be down or content is not available.")
        return jsonify(data)

@ns_channels.route('/<int:page_number>')
class Channels(Resource):
    @api.doc(description='Get channels for a specific page number')
    @api.response(200, 'Success', [channel_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_channels_page(page_number)
        if data is None:
            abort(500, description="Failed to scrape the channels page. The website might be down or content is not available.")
        return jsonify(data)

@ns_categories.route('/<int:page_number>')
class Categories(Resource):
    @api.doc(description='Get categories for a specific page number')
    @api.response(200, 'Success', [category_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_categories_page(page_number)
        if data is None:
            abort(500, description="Failed to scrape the categories page. The website might be down or content is not available.")
        return jsonify(data)

@ns_search.route('/<string:search_content>/<int:page_number>')
class SearchResults(Resource):
    @api.doc(description='Get search results for a specific query and page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid search content or page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, search_content, page_number):
        if not search_content:
            return jsonify({"error": "Search content cannot be empty."}), 400
        if page_number <= 0:
            return jsonify({"error": "Page number must be positive."}), 400
        data = scrape_hqporn_search_page(search_content, page_number)
        if data is None:
            abort(500, description="Failed to scrape the search results page. The website might be down or content is not available.")
        return jsonify(data)

@ns_stream.route('/<path:video_page_link>')
class StreamLinks(Resource):
    @api.doc(description='Get stream links for a specific video page URL')
    @api.response(200, 'Success', stream_model)
    @api.response(400, 'Invalid video page link')
    @api.response(404, 'Video player tag not found')
    @api.response(500, 'Failed to scrape the page')
    def get(self, video_page_link):
        if not video_page_link.startswith("http"):
            return jsonify({"error": f"Invalid video_page_link. It must be a full URL. Received: {video_page_link}"}), 400
        logger.info(f"Received request for video page link: {video_page_link}")
        data = scrape_video_page_for_streams(video_page_link)
        if data is None:
            abort(500, description="Failed to scrape the video page. The website might be down or content is not available.")
        if "error" in data and data.get("error") == "Video player tag not found.":
            return jsonify(data), 404
        return jsonify(data)

# Only change needed - ensure debug mode is OFF in production
if __name__ == '__main__':
    app.run(debug=False)  # Changed debug to False
