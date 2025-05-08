# scraper_api.py
import requests
from bs4 import BeautifulSoup
from flask import Flask, jsonify # Removed abort from flask, will use api.abort
from flask_restx import Api, Resource, fields
from flask_cors import CORS
import logging
from urllib.parse import quote # Removed unquote as it wasn't actively used for resolution
import os
from typing import List, Dict # Added typing for new function

# Pydantic for internal data structuring in the new scraper function
from pydantic import BaseModel

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__) # Corrected to use __name__ for Flask standard

app = Flask(__name__) # Corrected to use __name__
CORS(app)  # Enable CORS to allow requests from any origin

# Initialize Flask-RESTX for Swagger documentation
api = Api(
    app,
    version='1.0',
    title='HQ Porn Scraper API',
    description='A unified API for scraping fresh, best, trending videos, pornstars, channels, categories, search results, stream links, and generic page video extraction from hqporn.xxx',
    doc='/api/docs/'
)

BASE_URL = "https://hqporn.xxx"

# --- Pydantic models for the new generic scraper (internal use) ---
class ScrapedTag(BaseModel):
    link: str
    name: str

class ScrapedImageUrls(BaseModel):
    img_src: str
    jpeg: str
    webp: str

class ScrapedVideoData(BaseModel):
    duration: str
    gallery_id: str
    image_urls: ScrapedImageUrls
    link: str
    preview_video_url: str
    tags: List[ScrapedTag]
    thumb_id: str
    title: str
    title_attribute: str

# --- End Pydantic models ---


# Define namespaces for better organization in Swagger
ns_fresh = api.namespace('fresh', description='Operations related to fresh videos')
ns_best = api.namespace('best', description='Operations related to best-rated videos')
ns_trend = api.namespace('trend', description='Operations related to trending videos')
ns_pornstars = api.namespace('pornstars', description='Operations related to pornstars')
ns_channels = api.namespace('channels', description='Operations related to channels')
ns_categories = api.namespace('categories', description='Operations related to categories')
ns_search = api.namespace('search', description='Operations related to search results')
ns_stream = api.namespace('stream', description='Operations related to video stream links')
# New namespace for the generic URL scraper
ns_general_scrape = api.namespace('scrape_generic', description='Scrape videos from any provided hqporn.xxx page URL supporting the common thumbnail structure')


# Define data models for Swagger documentation
# Re-using existing video_model for the new endpoint's response
video_model = api.model('Video', {
    'link': fields.String(description='Video page URL'),
    'gallery_id': fields.String(description='Gallery ID'),
    'thumb_id': fields.String(description='Thumbnail ID'),
    'preview_video_url': fields.String(description='Preview video URL'),
    'title_attribute': fields.String(description='Title from link attribute or main title'),
    'title': fields.String(description='Video title'),
    'image_urls': fields.Nested(api.model('ImageURLs', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    })),
    'duration': fields.String(description='Video duration'),
    'tags': fields.List(fields.Nested(api.model('Tag', { # Note: Name 'Tag' here is fine for Flask-RESTX model
        'name': fields.String(description='Tag name'),
        'link': fields.String(description='Tag URL')
    })))
})

pornstar_model = api.model('Pornstar', {
    'link': fields.String(description='Pornstar page URL'),
    'pornstar_id': fields.String(description='Pornstar ID'),
    'name': fields.String(description='Pornstar name'),
    'image_urls': fields.Nested(api.model('ImageURLs_Pornstar', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

channel_model = api.model('Channel', {
    'link': fields.String(description='Channel page URL'),
    'channel_id': fields.String(description='Channel ID'),
    'name': fields.String(description='Channel name'),
    'image_urls': fields.Nested(api.model('ImageURLs_Channel', {
        'webp': fields.String(description='WebP image URL'),
        'jpeg': fields.String(description='JPEG image URL'),
        'img_src': fields.String(description='Image source URL')
    }))
})

category_model = api.model('Category', {
    'link': fields.String(description='Category page URL'),
    'category_id': fields.String(description='Category ID'),
    'title': fields.String(description='Category title'),
    'image_urls': fields.Nested(api.model('ImageURLs_Category', {
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

# Model for the generic scraper input URL
url_input_model = ns_general_scrape.model('UrlInput', {
    'url': fields.String(required=True, description='The full URL of the page to scrape for videos (must be from hqporn.xxx domain or similarly structured)')
})


# --- Scraper Functions ---

# New scraper function adapted from FastAPI input_file_0.py
def scrape_generic_page_videos(url: str, current_api_instance: Api) -> List[Dict]:
    """
    Scrapes video data from a generic webpage URL (expected to be hqporn.xxx or similar structure).
    Uses Pydantic models internally for data structuring.
    """
    logger.info(f"Attempting to scrape generic video page: {url}")
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes

        soup = BeautifulSoup(response.text, "html.parser")
        # Class from input_file_0.py
        video_items = soup.find_all("div", class_="b-thumb-item js-thumb-item js-thumb")

        if not video_items:
            # Check if the specific selector was the issue, vs an empty standard gallery
            gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
            if gallery_list_container:
                standard_items = gallery_list_container.find_all('div', class_='b-thumb-item')
                if not standard_items:
                    logger.info(f"No standard 'b-thumb-item' found in 'js-gallery-list' on {url} either.")
                else:
                    logger.info(f"Found 'b-thumb-item' under 'js-gallery-list', but not 'b-thumb-item js-thumb-item js-thumb'. The target class for generic scraper might be too specific for this page: {url}")

        videos_pydantic = []
        for item in video_items:
            if "random-thumb" in item.get("class", []): # Skip ads or random items
                continue

            title_elem = item.find("div", class_="b-thumb-item__title js-gallery-title")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            # Per input_file_0.py, title_attribute is same as title.
            # Existing Flask scrapers get it from link_tag.get('title').
            # For this generic one, let's see if link_tag provides it.
            
            link_elem = item.find("a", class_="js-gallery-stats js-gallery-link") # Standard link class in hqporn
            if not link_elem : # Fallback to any <a> tag with href if specific one not found
                 link_elem = item.find("a", href=True)


            title_attribute = title # Default as per FastAPI file
            if link_elem and link_elem.get('title'):
                title_attribute = link_elem.get('title').strip() # Prefer <a> tag's title for title_attribute

            duration_elem = item.find("div", class_="b-thumb-item__duration")
            duration = duration_elem.find("span").get_text(strip=True) if duration_elem and duration_elem.find("span") else "N/A"

            img_elem = item.find("img") # General image
            img_src = ""
            jpeg = ""
            webp = ""

            picture_tag = item.find('picture', class_='js-gallery-img') # More specific image structure
            if picture_tag:
                source_webp_tag = picture_tag.find('source', attrs={'type': 'image/webp'})
                webp = source_webp_tag['srcset'] if source_webp_tag and source_webp_tag.has_attr('srcset') else ''
                source_jpeg_tag = picture_tag.find('source', attrs={'type': 'image/jpeg'})
                jpeg = source_jpeg_tag['srcset'] if source_jpeg_tag and source_jpeg_tag.has_attr('srcset') else ''
                img_tag_in_picture = picture_tag.find('img')
                if img_tag_in_picture:
                    img_src = img_tag_in_picture.get('data-src', img_tag_in_picture.get('src', ''))
            elif img_elem and "src" in img_elem.attrs: # Fallback to simple img src
                 img_src = img_elem["src"]
                 jpeg = img_src # If only img_src, use it for jpeg as well. Webp might be empty.
            
            # Further refined based on input_file_0.py if general methods above fail
            if not jpeg and not webp and img_elem: # Use FastAPI logic if picture_tag wasn't specific enough
                img_src_from_fastapi = img_elem["src"] if img_elem and "src" in img_elem.attrs else ""
                jpeg_source = item.find("source", type="image/jpeg")
                webp_source = item.find("source", type="image/webp")
                jpeg_from_fastapi = jpeg_source["srcset"] if jpeg_source and "srcset" in jpeg_source.attrs else img_src_from_fastapi
                webp_from_fastapi = webp_source["srcset"] if webp_source and "srcset" in webp_source.attrs else ""
                
                if not img_src: img_src = img_src_from_fastapi
                if not jpeg: jpeg = jpeg_from_fastapi
                if not webp: webp = webp_from_fastapi


            link = ""
            gallery_id = "Unknown"
            preview_video_url = ""
            thumb_id = "Unknown"

            if link_elem:
                href = link_elem.get("href", "")
                link = href if href.startswith("http") else (f"{BASE_URL}{href}" if href else "")
                gallery_id = link_elem.get("data-gallery-id", "Unknown")
                preview_video_url = link_elem.get("data-preview", "")
                thumb_id = link_elem.get("data-thumb-id", "Unknown")


            tags_data = []
            categories_elem = item.find("div", class_="b-thumb-item__detail")
            if categories_elem:
                category_links = categories_elem.find_all("a")
                for cat_link_elem in category_links:
                    cat_href = cat_link_elem.get("href", "")
                    cat_name = cat_link_elem.get_text(strip=True)
                    full_cat_link = cat_href if cat_href.startswith("http") else (f"{BASE_URL}{cat_href}" if cat_href else "")
                    if cat_name and full_cat_link:
                        tags_data.append(ScrapedTag(link=full_cat_link, name=cat_name))
            
            # Create ScrapedVideoData object
            video_pydantic_obj = ScrapedVideoData(
                duration=duration,
                gallery_id=gallery_id,
                image_urls=ScrapedImageUrls(
                    img_src=img_src,
                    jpeg=jpeg,
                    webp=webp
                ),
                link=link,
                preview_video_url=preview_video_url,
                tags=tags_data,
                thumb_id=thumb_id,
                title=title,
                title_attribute=title_attribute # Uses refined title_attribute
            )
            videos_pydantic.append(video_pydantic_obj)
        
        return [video.dict() for video in videos_pydantic]

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching webpage {url} for generic scrape: {str(e)}")
        current_api_instance.abort(500, detail=f"Error fetching webpage: {str(e)}") # Use detail for FastAPI like error
    except Exception as e:
        logger.error(f"Error processing webpage {url} for generic scrape: {str(e)}")
        current_api_instance.abort(500, detail=f"Error processing webpage: {str(e)}")


def scrape_hqporn_fresh_page(page_number):
    scrape_url = f"{BASE_URL}/fresh/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/fresh/"

    logger.info(f"Attempting to scrape (fresh/newest): {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

def scrape_hqporn_best_page(page_number):
    scrape_url = f"{BASE_URL}/best/{page_number}/"
    if page_number == 1: scrape_url = f"{BASE_URL}/best/"
    logger.info(f"Attempting to scrape (best/top-rated): {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
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
    for item_soup in items: # Same structure as fresh, could be refactored
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

def scrape_hqporn_trend_page(page_number):
    scrape_url = f"{BASE_URL}/trend/{page_number}/" # Added trailing slash consistency based on fresh/best
    if page_number == 1: scrape_url = f"{BASE_URL}/trend/" # For page 1 use base trend URL
    logger.info(f"Attempting to scrape (trending): {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
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
        logger.info(f"No items found on page {page_number} of /trend/.")
        return []
    scraped_data = [] # Same structure as fresh/best
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

def scrape_hqporn_pornstars_page(page_number):
    scrape_url = f"{BASE_URL}/pornstars/{page_number}/"
    if page_number == 1: scrape_url = f"{BASE_URL}/pornstars/"
    logger.info(f"Attempting to scrape pornstars from: {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list') # Corrected id to 'galleries' based on general site structure; class differentiates
    if not pornstar_list_container:
        logger.warning(f"Pornstar list container (div#galleries.js-pornstar-list) not found on {scrape_url}.")
        return []
    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')
    if not items:
        logger.info(f"No pornstar items found on page {page_number}.")
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
        else: continue
        title_div = item_soup.find('div', class_='b-thumb-item__title') # This typically holds the name too
        if title_div and title_div.get_text(strip=True) and not data.get('name'): data['name'] = title_div.get_text(strip=True)
        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag: image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls
        if data.get('name') and data.get('link'): scraped_data.append(data)
    return scraped_data

def scrape_hqporn_channels_page(page_number):
    scrape_url = f"{BASE_URL}/channels/{page_number}/"
    if page_number == 1: scrape_url = f"{BASE_URL}/channels/"
    logger.info(f"Attempting to scrape channels from: {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list') # Corrected id to 'galleries'
    if not channel_list_container:
        logger.warning(f"Channel list container (div#galleries.js-channel-list) not found on {scrape_url}.")
        return []
    items = channel_list_container.find_all('div', class_='b-thumb-item--cat') # Class for channels and categories
    if not items:
        logger.info(f"No channel items found on page {page_number}.")
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
        else: continue
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span')
            if title_span and title_span.get_text(strip=True): data['name'] = title_span.get_text(strip=True)
            elif not data.get('name') and title_div.get_text(strip=True): data['name'] = title_div.get_text(strip=True)
        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag: image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls
        if data.get('name') and data.get('link'): scraped_data.append(data)
    return scraped_data

def scrape_hqporn_categories_page(page_number):
    scrape_url = f"{BASE_URL}/categories/{page_number}/" # Added trailing slash consistency
    if page_number == 1: scrape_url = f"{BASE_URL}/categories/"
    logger.info(f"Attempting to scrape categories from: {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    category_list_container = soup.find('div', id='galleries', class_='js-category-list') # Corrected id
    if not category_list_container:
        logger.warning(f"Category list container (div#galleries.js-category-list) not found on {scrape_url}.")
        return []
    items = category_list_container.find_all('div', class_='b-thumb-item--cat')
    if not items:
        logger.info(f"No category items found on page {page_number}.")
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
        else: continue
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True) and not data.get('title'): data['title'] = title_div.get_text(strip=True)
        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag: image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = image_urls
        if data.get('title') and data.get('link'): scraped_data.append(data)
    return scraped_data

def scrape_hqporn_search_page(search_content, page_number):
    safe_search_content = quote(search_content)
    scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/"
    if page_number == 1: scrape_url = f"{BASE_URL}/search/{safe_search_content}/"
    logger.info(f"Attempting to scrape search results for '{search_content}' (page {page_number}): {scrape_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        return None
    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on search page {scrape_url}.")
        return [] # Assume no results if container missing after successful HTTP GET
    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found for search '{search_content}' on page {page_number}.")
        return []
    scraped_data = [] # Same structure as fresh/best/trend
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
                    tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                    tags_list.append({'name': tag_name, 'link': tag_link_full})
        data['tags'] = tags_list
        scraped_data.append(data)
    return scraped_data

def scrape_video_page_for_streams(video_page_url):
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    stream_data_template = lambda error=None, note=None: {
        "video_page_url": video_page_url, "main_video_src": None, 
        "source_tags": [], "poster_image": None, "sprite_previews": [],
        "error": error, "note": note
    }
    try:
        response = requests.get(video_page_url, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {video_page_url}: {e}")
        return stream_data_template(error=f"Failed to fetch page: {e}")
    soup = BeautifulSoup(response.content, 'html.parser')
    stream_data = stream_data_template() # Initialize with structure
    video_tag = soup.find('video', id='video_html5_api') or soup.find('div', class_='b-video-player') and soup.find('div', class_='b-video-player').find('video')
    if not video_tag:
        logger.warning(f"Video player tag not found on {video_page_url}.")
        stream_data["error"] = "Video player tag not found."
        return stream_data
    if video_tag.has_attr('src') and video_tag['src'] and not video_tag['src'].startswith('blob:'):
        stream_data["main_video_src"] = video_tag['src']
    source_elements = video_tag.find_all('source')
    processed_src_urls = set()
    if stream_data["main_video_src"]: processed_src_urls.add(stream_data["main_video_src"])
    
    temp_sources = []
    # If main_video_src was directly on video tag, and no identical <source> tags will cover it
    # add it as a source item.
    main_src_is_also_in_source_tags = False
    for source_el in source_elements:
        if source_el.get('src') == stream_data["main_video_src"]:
            main_src_is_also_in_source_tags = True
            break
    if stream_data["main_video_src"] and not main_src_is_also_in_source_tags:
         temp_sources.append({
            "src": stream_data["main_video_src"],
            "type": video_tag.get('type', 'video/mp4'), # Default or guess type
            "size": None # Size usually not on video tag
        })
         processed_src_urls.add(stream_data["main_video_src"])

    for source_el in source_elements:
        src_url = source_el.get('src')
        if src_url and not src_url.startswith('blob:') and src_url not in processed_src_urls:
            temp_sources.append({
                "src": src_url,
                "type": source_el.get('type'),
                "size": source_el.get('data-size', source_el.get('size'))
            })
            processed_src_urls.add(src_url)
    stream_data["source_tags"] = temp_sources
    if video_tag.has_attr('poster'): stream_data["poster_image"] = video_tag['poster']
    if video_tag.has_attr('data-preview'): # Sprite previews
        stream_data["sprite_previews"] = [s.strip() for s in video_tag['data-preview'].split(',') if s.strip()]
    if not stream_data["source_tags"] and not stream_data["main_video_src"] and "error" not in stream_data:
        # Try to find sources in script tags as a fallback note
        scripts = soup.find_all('script', string=True) # only inline scripts
        for script in scripts:
            if "player.src({ src:" in script.string or "new Playerjs(" in script.string:
                logger.info(f"Potential dynamic video source in script on {video_page_url}")
                stream_data["note"] = (stream_data.get("note","") + " Video source might be embedded in JavaScript.").strip()
                break
        if not stream_data.get("note") and "error" not in stream_data: # if no script hint and no other error
            stream_data["note"] = (stream_data.get("note","") + " No direct video <src> or <source> tags found.").strip()
    return stream_data


# --- API Endpoints ---
@ns_fresh.route('/<int:page_number>')
class FreshVideos(Resource):
    @ns_fresh.doc(description='Get fresh videos for a specific page number')
    @ns_fresh.marshal_list_with(video_model) # Use marshal_list_with for list responses
    @ns_fresh.response(400, 'Invalid page number')
    @ns_fresh.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_fresh_page(page_number)
        if data is None: api.abort(500, "Failed to scrape fresh videos page.")
        return data # jsonify is not needed when using marshal_list_with or marshal_with

@ns_best.route('/<int:page_number>')
class BestVideos(Resource):
    @ns_best.doc(description='Get best-rated videos for a specific page number')
    @ns_best.marshal_list_with(video_model)
    @ns_best.response(400, 'Invalid page number')
    @ns_best.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_best_page(page_number)
        if data is None: api.abort(500, "Failed to scrape best videos page.")
        return data

@ns_trend.route('/<int:page_number>')
class TrendVideos(Resource):
    @ns_trend.doc(description='Get trending videos for a specific page number')
    @ns_trend.marshal_list_with(video_model)
    @ns_trend.response(400, 'Invalid page number')
    @ns_trend.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_trend_page(page_number)
        if data is None: api.abort(500, "Failed to scrape trending videos page.")
        return data

@ns_pornstars.route('/<int:page_number>')
class Pornstars(Resource):
    @ns_pornstars.doc(description='Get pornstars for a specific page number')
    @ns_pornstars.marshal_list_with(pornstar_model)
    @ns_pornstars.response(400, 'Invalid page number')
    @ns_pornstars.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_pornstars_page(page_number)
        if data is None: api.abort(500, "Failed to scrape pornstars page.")
        return data

@ns_channels.route('/<int:page_number>')
class Channels(Resource):
    @ns_channels.doc(description='Get channels for a specific page number')
    @ns_channels.marshal_list_with(channel_model)
    @ns_channels.response(400, 'Invalid page number')
    @ns_channels.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_channels_page(page_number)
        if data is None: api.abort(500, "Failed to scrape channels page.")
        return data

@ns_categories.route('/<int:page_number>')
class Categories(Resource):
    @ns_categories.doc(description='Get categories for a specific page number')
    @ns_categories.marshal_list_with(category_model)
    @ns_categories.response(400, 'Invalid page number')
    @ns_categories.response(500, 'Failed to scrape the page')
    def get(self, page_number):
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_categories_page(page_number)
        if data is None: api.abort(500, "Failed to scrape categories page.")
        return data

@ns_search.route('/<string:search_content>/<int:page_number>')
class SearchResults(Resource):
    @ns_search.doc(description='Get search results for a specific query and page number')
    @ns_search.marshal_list_with(video_model)
    @ns_search.response(400, 'Invalid search content or page number')
    @ns_search.response(500, 'Failed to scrape the page')
    def get(self, search_content, page_number):
        if not search_content: api.abort(400, "Search content cannot be empty.")
        if page_number <= 0: api.abort(400, "Page number must be positive.")
        data = scrape_hqporn_search_page(search_content, page_number)
        if data is None: api.abort(500, "Failed to scrape search results page.")
        return data

@ns_stream.route('/<path:video_page_link>') # Using <path:> to capture full URLs including slashes
class StreamLinks(Resource):
    @ns_stream.doc(description='Get stream links for a video page URL. URL must be fully qualified.', 
                   params={'video_page_link': 'Full URL of the video page (e.g., https://hqporn.xxx/video/...)'})
    @ns_stream.marshal_with(stream_model) # Singular item
    @ns_stream.response(400, 'Invalid video page link')
    @ns_stream.response(404, 'Video player tag or stream sources not found') # Corrected 404 meaning
    @ns_stream.response(500, 'Failed to scrape the page or error during scraping')
    def get(self, video_page_link):
        # Flask-RESTX path converter handles URL decoding automatically.
        # Ensure the link is a complete URL starting with http(s)
        if not (video_page_link.startswith("http://") or video_page_link.startswith("https://")):
             # If it doesn't start with http, assume it might be missing (e.g. user provided 'hqporn.xxx/video/...')
             # Try to prepend https://
             if video_page_link.startswith(BASE_URL.replace("https://","").replace("http://","")):
                 video_page_link = "https://" + video_page_link
             else: # if not even the base domain, it is truly malformed.
                 api.abort(400, f"Invalid video_page_link. It must be a full URL. Received: {video_page_link}")

        logger.info(f"StreamLinks: Received request for video page link: {video_page_link}")
        data = scrape_video_page_for_streams(video_page_link)

        if data.get("error") == "Video player tag not found.":
            api.abort(404, data["error"], **data) # Pass through original error and context
        elif data.get("error") and "Failed to fetch page" in data["error"]:
            api.abort(500, data["error"], **data)
        
        # If no explicit error, but also no sources
        if not data.get("main_video_src") and not data.get("source_tags") and not data.get("error"):
            # Return 200 with data noting no streams found, or 404
            # For consistency, if no streams are found but page loaded, this can be considered "not found" for stream data
            data["error"] = data.get("error", "No usable video stream sources found on the page.") # Add error if not already there
            # Let's still return 200 but with the error field populated, marshal_with will handle it
            # If a strict 404 is desired for "no streams found on valid page", then api.abort(404, ...) here
        
        return data

# New endpoint for generic video scraping by URL
@ns_general_scrape.route('/scrape-videos')
class GenericVideoScraper(Resource):
    @ns_general_scrape.doc(description='Scrape video data from a provided hqporn.xxx URL (or similarly structured page) and return a list of video metadata.')
    @ns_general_scrape.expect(url_input_model, validate=True)
    @ns_general_scrape.marshal_list_with(video_model)
    @ns_general_scrape.response(400, 'Invalid input URL')
    @ns_general_scrape.response(404, 'No videos found on the provided webpage')
    @ns_general_scrape.response(500, 'Error fetching or processing the webpage')
    def post(self):
        target_url = api.payload.get('url')
        if not target_url or not (target_url.startswith("http://") or target_url.startswith("https://")):
            api.abort(400, "A valid, full URL starting with http:// or https:// must be provided.")
        
        # Optionally, restrict to BASE_URL domain or warn
        # if not target_url.startswith(BASE_URL):
        #     logger.warning(f"Generic scrape target URL {target_url} is outside of {BASE_URL}. Scraper might not work as expected.")

        videos_data = scrape_generic_page_videos(target_url, current_api_instance=api) # Pass api instance for abort
        
        if not videos_data: # Handles both empty list and None (though abort should prevent None)
            api.abort(404, "No videos found on the provided webpage, or the page structure is not recognized by this scraper.")
            
        return videos_data


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080)) # Changed default port slightly for distinction
    debug_mode_env = os.environ.get('FLASK_DEBUG', 'true').lower() # Default to true for local dev
    debug_mode = debug_mode_env in ['1', 'true', 'on', 'yes']
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
print("Full API code with the new endpoint integrated is ready.")
