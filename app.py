# scraper_api.py

import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify, abort
from flask_restx import Api, Resource, fields
from flask_cors import CORS
import logging
from urllib.parse import quote, unquote
import uuid # Note: uuid is imported but not used. Can be removed if not planned for use.
import os # Added for environment variable access

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
    'image_urls': fields.Nested(api.model('ImageURLs_Pornstar', { # Renamed to avoid Swagger duplicate model name error
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

channel_model = api.model('Channel', {
    'link': fields.String(description='Channel page URL'),
    'channel_id': fields.String(description='Channel ID'),
    'name': fields.String(description='Channel name'),
    'image_urls': fields.Nested(api.model('ImageURLs_Channel', { # Renamed to avoid Swagger duplicate model name error
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

category_model = api.model('Category', {
    'link': fields.String(description='Category page URL'),
    'category_id': fields.String(description='Category ID'),
    'title': fields.String(description='Category title'),
    'image_urls': fields.Nested(api.model('ImageURLs_Category', { # Renamed to avoid Swagger duplicate model name error
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
    scrape_url = f"{BASE_URL}/trend/{page_number}" # Removed trailing slash if page_number is present for consistency.

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
                # Use title from span if available and seems more accurate
                data['name'] = title_span.get_text(strip=True)
            elif not data.get('name') and title_div.get_text(strip=True): # Fallback to div text if link title was empty
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
            logger.warning(f"Skipping channel item due to missing name or link: {item_soup.prettify()}")

    return scraped_data

def scrape_hqporn_categories_page(page_number):
    """
    Scrapes a specific page number from hqporn.xxx/categories/
    """
    scrape_url = f"{BASE_URL}/categories/{page_number}" # Removed trailing slash if page_number is present.
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
            data['title'] = link_tag.get('title', '').strip() # Prefer title from link attribute
        else:
            logger.warning("Found a category item with no js-category-stats link.")
            continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True):
            title_from_div = title_div.get_text(strip=True)
            if not data.get('title'): # Use title from div only if link attribute was empty/missing
                 data['title'] = title_from_div
            elif title_from_div and data.get('title') and title_from_div != data.get('title'): # Log if they differ significantly
                 logger.debug(f"Title mismatch for category {data['link']}: link '{data.get('title')}', div '{title_from_div}'")


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
        # Return stream_data with an error, rather than None, to provide context
        return { 
            "video_page_url": video_page_url, 
            "error": f"Failed to fetch page: {e}",
            "main_video_src": None, "source_tags": [], "poster_image": None, "sprite_previews": []
        }


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
        stream_data["error"] = "Video player tag not found."
        return stream_data # Return data with error message

    # Prefer src from <video> tag if present and not just a placeholder
    if video_tag.has_attr('src') and video_tag['src'] and not video_tag['src'].startswith('blob:'):
        stream_data["main_video_src"] = video_tag['src']
        # Add to source_tags only if it's not already going to be captured by <source> tags logic
        # This ensures it's listed if it's the *only* source.
        temp_source_list_for_check = [s.get('src') for s in video_tag.find_all('source') if s.has_attr('src')]
        if video_tag['src'] not in temp_source_list_for_check:
             stream_data["source_tags"].append({
                "src": video_tag['src'],
                "type": video_tag.get('type', 'video/mp4'), # Guess type if not specified
                "size": None # Size is not usually on the video tag directly
            })


    source_tags = video_tag.find_all('source')
    found_sources_urls = set()
    if stream_data["main_video_src"]: # Add main_video_src to ensure it's treated as found
        found_sources_urls.add(stream_data["main_video_src"])
    
    # Process existing source_tags first from video_tag['src'] (if it was added)
    temp_source_tags_list = []
    for s_item in stream_data["source_tags"]:
        if s_item['src'] not in found_sources_urls:
            temp_source_tags_list.append(s_item)
            found_sources_urls.add(s_item['src'])
    
    # Then process <source> elements
    for source_tag in source_tags:
        if source_tag.has_attr('src'):
            src_url = source_tag['src']
            if src_url and src_url not in found_sources_urls and not src_url.startswith('blob:'):
                temp_source_tags_list.append({
                    "src": src_url,
                    "type": source_tag.get('type'),
                    "size": source_tag.get('data-size', source_tag.get('size')) # Prefer data-size if present
                })
                found_sources_urls.add(src_url)
    
    stream_data["source_tags"] = temp_source_tags_list # Replace with the unique list

    if video_tag.has_attr('poster'):
        stream_data["poster_image"] = video_tag['poster']

    # Sprite previews are often in data-preview attribute
    if video_tag.has_attr('data-preview'):
        sprite_string = video_tag['data-preview']
        stream_data["sprite_previews"] = [sprite.strip() for sprite in sprite_string.split(',') if sprite.strip()]
    
    if not stream_data["source_tags"] and not stream_data["main_video_src"]:
        # Check for alternative ways scripts might embed video data
        scripts = soup.find_all('script')
        found_in_script = False
        for script in scripts:
            if script.string: # Only consider inline scripts
                if "player.src({ src:" in script.string: # Common pattern for some JS players
                    # This requires more complex parsing, regex might be needed
                    # For now, just indicate a potential script source
                    logger.info(f"Potential video source found in script tag on {video_page_url}")
                    stream_data["note"] = "Video source might be embedded in JavaScript. Manual inspection needed."
                    found_in_script = True
                    break
        if not found_in_script and "error" not in stream_data: # Only add this note if no other error/note exists
             logger.warning(f"No direct video src or source tags found for video on {video_page_url}.")
             stream_data["note"] = "No direct video <src> or <source> tags found. Video may be loaded dynamically."


    # If main_video_src was populated from video tag but no source tags, ensure it's listed.
    # Redundant due to earlier logic change but kept as a safeguard thought process.
    # if stream_data["main_video_src"] and not stream_data["source_tags"]:
    #    stream_data["source_tags"].append({"src": stream_data["main_video_src"], "type": "video/mp4", "size": None})


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
            # Using Flask-RESTX abort for consistent error responses
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_fresh_page(page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the page. The website might be down or content is not available.")
        return jsonify(data)

@ns_best.route('/<int:page_number>')
class BestVideos(Resource):
    @api.doc(description='Get best-rated videos for a specific page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_best_page(page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the page. The website might be down or content is not available.")
        return jsonify(data)

@ns_trend.route('/<int:page_number>')
class TrendVideos(Resource):
    @api.doc(description='Get trending videos for a specific page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_trend_page(page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the page. The website might be down or content is not available.")
        return jsonify(data)

@ns_pornstars.route('/<int:page_number>')
class Pornstars(Resource):
    @api.doc(description='Get pornstars for a specific page number')
    @api.response(200, 'Success', [pornstar_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_pornstars_page(page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the pornstars page. The website might be down or content is not available.")
        return jsonify(data)

@ns_channels.route('/<int:page_number>')
class Channels(Resource):
    @api.doc(description='Get channels for a specific page number')
    @api.response(200, 'Success', [channel_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_channels_page(page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the channels page. The website might be down or content is not available.")
        return jsonify(data)

@ns_categories.route('/<int:page_number>')
class Categories(Resource):
    @api.doc(description='Get categories for a specific page number')
    @api.response(200, 'Success', [category_model])
    @api.response(400, 'Invalid page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0:
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_categories_page(page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the categories page. The website might be down or content is not available.")
        return jsonify(data)

@ns_search.route('/<string:search_content>/<int:page_number>')
class SearchResults(Resource):
    @api.doc(description='Get search results for a specific query and page number')
    @api.response(200, 'Success', [video_model])
    @api.response(400, 'Invalid search content or page number')
    @api.response(500, 'Failed to scrape the page')
    def get(self, search_content, page_number):
        if not search_content:
            api.abort(400, "Search content cannot be empty.")
        if page_number <= 0:
            api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_search_page(search_content, page_number)
        if data is None:
            api.abort(500, description="Failed to scrape the search results page. The website might be down or content is not available.")
        return jsonify(data)

@ns_stream.route('/<path:video_page_link>')
class StreamLinks(Resource):
    @api.doc(description='Get stream links for a specific video page URL. The URL should be fully qualified (e.g., https://...).')
    @api.response(200, 'Success', stream_model)
    @api.response(400, 'Invalid video page link')
    @api.response(404, 'Video player tag or stream sources not found')
    @api.response(500, 'Failed to scrape the page or error during scraping')
    def get(self, video_page_link):
        # Flask-RESTx automatically decodes the path, so 'video_page_link' is already unquoted.
        # However, the link might contain scheme (http/https) which is part of the path.
        # Ensure it is a full URL.
        if not (video_page_link.startswith("http://") or video_page_link.startswith("https://")):
             api.abort(400, f"Invalid video_page_link. It must be a full URL. Received: {video_page_link}")
        
        logger.info(f"Received request for video page link: {video_page_link}")
        data = scrape_video_page_for_streams(video_page_link)

        if data is None: # Should ideally not happen if scrape_video_page_for_streams always returns a dict
            api.abort(500, description="An unexpected error occurred while scraping the video page.")
        
        # If an error was set by the scraper function itself (e.g., network error, critical parsing error)
        if "error" in data and data.get("error") == "Video player tag not found.":
            # Using Flask-RESTX abort for standard error responses
            api.abort(404, data.get("error"), **data) # Pass along other data like page URL

        if "error" in data and "Failed to fetch page" in data.get("error", ""):
             api.abort(500, description=data.get("error"), **data)

        # If no sources and no main video, but also no specific "error" like "tag not found"
        if not data.get("source_tags") and not data.get("main_video_src") and "error" not in data:
            if "note" not in data or "dynamically" not in data["note"]: # if not already noted as dynamic loading
                data["note"] = (data.get("note","") + " No usable video stream sources found. ").strip()
            # Consider returning 404 if it's definitively no streams. 200 with a note is also an option.
            # For now, let's return 200 but with a clear note or error message in the payload.
            # If no other error and no sources are found.
            if "error" not in data: # Prevent overwriting specific errors like "tag not found"
                 data["error"] = "No streamable video sources found on the page."
            return jsonify(data), 200 # Or 404 if strictly no content found

        return jsonify(data)


if __name__ == '__main__':
    # The following is primarily for local development and testing.
    # For production on platforms like Render.com, a WSGI server like Gunicorn is recommended.
    # Render.com Start Command Example: gunicorn scraper_api:app
    # Gunicorn will handle host/port binding based on Render's environment (e.g., $PORT).
    
    # Import os here if not already at the top of the file
    # import os 
    
    port = int(os.environ.get('PORT', 5000)) # Default to 5000 if PORT not set
    
    # Debug mode should be False in production.
    # Set FLASK_DEBUG=1 or true in your local environment to enable it.
    debug_mode_env = os.environ.get('FLASK_DEBUG', 'false').lower()
    debug_mode = debug_mode_env in ['1', 'true', 'on', 'yes']
    
    # For local testing, you might want to enable debug mode:
    # app.run(host='0.0.0.0', port=port, debug=True)
    # For simulated production-like local run (respecting FLASK_DEBUG):
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
