# main.py

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Path, Query # MODIFIED: Added Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field 
from typing import List, Optional, Any # Dict removed as not directly used by models here
from urllib.parse import quote 
import logging
import re # ADDED: For the new /scrape endpoint logic

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- FastAPI App Setup ---
# Enable docs at /docs and /redoc automatically
app = FastAPI(title="Consolidated HQPORN Scraper API")

# Add CORS middleware to allow cross-origin requests from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allows all origins
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Constants ---
BASE_URL = "https://hqporn.xxx"
# Define standard headers once to avoid repetition
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# --- Pydantic Models ---
# These define the expected structure of request bodies and response data

class ImageUrls(BaseModel):
    """Model for image URLs associated with items (videos, categories, etc.)"""
    img_src: Optional[str] = Field(None, description="Main image source URL (often for default display or lazy loading)")
    jpeg: Optional[str] = Field(None, description="Source URL for JPEG image, often with srcset quality information")
    webp: Optional[str] = Field(None, description="Source URL for WebP image, often with srcset quality information")

class Tag(BaseModel):
    """Model for individual tags/categories associated with a video."""
    link: Optional[str] = Field(None, description="Link to the tag's page.")
    name: Optional[str] = Field(None, description="Name of the tag.")

class VideoData(BaseModel): # This model is used for the new endpoint's response items, acting as "Gallery"
    """Model for video item data."""
    duration: Optional[str] = Field(None, description="Duration of the video (e.g., '12:34').")
    gallery_id: Optional[str] = Field(None, description="Unique ID for the video gallery/item on the site.")
    image_urls: ImageUrls
    link: Optional[str] = Field(None, description="Link to the full video page.")
    preview_video_url: Optional[str] = Field(None, description="URL for a short preview video.")
    tags: List[Tag] = Field([], description="List of tags/categories associated with the video.")
    thumb_id: Optional[str] = Field(None, description="Unique ID for the thumbnail/preview item.")
    title: Optional[str] = Field(None, description="Title of the video. For the /scrape GET endpoint, this is a space-removed version of title_attribute. For other endpoints, it's usually the display title.")
    title_attribute: Optional[str] = Field(None, description="Value of the title attribute from the link tag (often the full video title).")

class ScrapeRequest(BaseModel):
    """Model for the request body when requesting a generic page scrape via POST /scrape-videos."""
    url: str = Field(..., description="The URL of the page to scrape.")

class CategoryData(BaseModel):
    """Model for category item data."""
    link: Optional[str] = Field(None, description="Link to the category's listing page.")
    category_id: Optional[str] = Field(None, description="Unique ID for the category.")
    title: Optional[str] = Field(None, description="Name or title of the category.")
    image_urls: ImageUrls

class PornstarData(BaseModel):
    """Model for pornstar item data."""
    link: Optional[str] = Field(None, description="Link to the pornstar's page.")
    pornstar_id: Optional[str] = Field(None, description="Unique ID for the pornstar.")
    name: Optional[str] = Field(None, description="Name of the pornstar.")
    image_urls: ImageUrls

class ChannelData(BaseModel):
    """Model for channel item data."""
    link: Optional[str] = Field(None, description="Link to the channel's listing page.")
    channel_id: Optional[str] = Field(None, description="Unique ID for the channel.")
    name: Optional[str] = Field(None, description="Name of the channel.")
    image_urls: ImageUrls

class StreamSource(BaseModel):
    """Model for a single video source tag."""
    src: Optional[str] = Field(None, description="URL of the video stream.")
    type: Optional[str] = Field(None, description="MIME type of the stream (e.g., 'video/mp4').")
    size: Optional[str] = Field(None, description="Video size/quality if available (e.g., '720').")

class StreamData(BaseModel):
    """Model for data scraped from a single video playback page."""
    video_page_url: str = Field(..., description="The URL of the page that was scraped.")
    main_video_src: Optional[str] = Field(None, description="The primary video source URL from the video tag's src attribute.")
    source_tags: List[StreamSource] = Field([], description="List of source tags with different qualities/types.")
    poster_image: Optional[str] = Field(None, description="URL of the video poster image.")
    sprite_previews: List[str] = Field([], description="List of sprite image URLs for video previews.")
    note: Optional[str] = Field(None, description="Additional notes, e.g., if direct streams were not found.")


# --- Helper Scraping Functions ---

def safe_scrape_page(url: str) -> BeautifulSoup:
    """Fetches a URL and returns a BeautifulSoup object. Raises HTTPException on error."""
    logger.info(f"Fetching: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return BeautifulSoup(response.content, 'html.parser')
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch or parse URL: {url} - {str(e)}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during scraping or parsing {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred while scraping or parsing {url}: {str(e)}")

def extract_image_urls(item_soup: BeautifulSoup) -> ImageUrls:
    """Extracts ImageUrls model from an item's BeautifulSoup element."""
    picture_tag = item_soup.find('picture', class_='js-gallery-img')
    if not picture_tag:
         picture_tag = item_soup.find('picture') # Fallback for other item types

    img_urls_data = {} 
    if picture_tag:
        source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
        if source_webp and source_webp.has_attr('srcset'):
            img_urls_data['webp'] = source_webp['srcset']

        source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
        if source_jpeg and source_jpeg.has_attr('srcset'):
            img_urls_data['jpeg'] = source_jpeg['srcset']

        img_tag = picture_tag.find('img')
        if img_tag:
            img_src_val = img_tag.get('data-src', img_tag.get('src'))
            if img_src_val:
                 img_urls_data['img_src'] = img_src_val
    
    return ImageUrls(**img_urls_data)

# --- NEW HELPER FUNCTIONS FOR /scrape (GET) ENDPOINT ---

def extract_gallery_data_from_item(item_soup: BeautifulSoup) -> Optional[VideoData]:
    """
    Extracts gallery item data from a BeautifulSoup representation of a 'div.b-thumb-item'.
    This function is specific to the logic required by the /scrape (GET) endpoint,
    particularly the 'title' field generation.
    """
    link_tag = item_soup.find('a', class_='js-gallery-stats')
    
    if not link_tag:
        logger.debug(f"Item skipped for /scrape endpoint: 'a.js-gallery-stats' not found in {item_soup.name} with classes {item_soup.get('class', [])}.")
        return None

    href = link_tag.get('href')
    link = None
    if href:
        link = f"{BASE_URL}{href}" if href.startswith('/') else href

    gallery_id = link_tag.get('data-gallery-id')

    title_attribute_val = link_tag.get('title') 
    cleaned_main_title = None
    if title_attribute_val:
        cleaned_main_title = re.sub(r'\s+', '', title_attribute_val)

    duration_tag = item_soup.find('div', class_='b-thumb-item__duration')
    duration_span = duration_tag.find('span') if duration_tag else None
    duration = duration_span.get_text(strip=True) if duration_span else None

    image_urls_model = extract_image_urls(item_soup)
    preview_video_url_val = link_tag.get('data-preview')
    thumb_id_val = link_tag.get('data-thumb-id')

    tags_list = []
    detail_tag = item_soup.find('div', class_='b-thumb-item__detail')
    if detail_tag:
        tag_links_in_detail = detail_tag.find_all('a')
        for tag_a in tag_links_in_detail:
            tag_name_text = tag_a.get_text(strip=True)
            tag_href = tag_a.get('href')
            if tag_href and tag_name_text:
                full_tag_link = f"{BASE_URL}{tag_href}" if tag_href.startswith('/') else tag_href
                tags_list.append(Tag(link=full_tag_link, name=tag_name_text))

    if link:
        return VideoData(
            duration=duration,
            gallery_id=gallery_id,
            image_urls=image_urls_model,
            link=link,
            preview_video_url=preview_video_url_val,
            tags=tags_list,
            thumb_id=thumb_id_val,
            title=cleaned_main_title,
            title_attribute=title_attribute_val
        )
    else:
        logger.warning(f"Skipping gallery item for /scrape endpoint due to missing link from 'a.js-gallery-stats'.")
        return None

def scrape_url_for_gallery_data(url: str) -> List[VideoData]:
    """
    Scrapes a given URL for gallery data, expecting items in 'div.b-thumb-item' format.
    Uses `extract_gallery_data_from_item` for parsing individual items.
    This is the main worker function for the /scrape (GET) endpoint.
    """
    logger.info(f"Attempting to scrape gallery data from URL for /scrape endpoint: {url}")
    soup = safe_scrape_page(url)

    gallery_item_divs = soup.find_all('div', class_='b-thumb-item')
    
    if not gallery_item_divs:
        logger.info(f"No 'div.b-thumb-item' elements found on {url} for /scrape. Returning empty list.")
        return []

    scraped_galleries = []
    for item_div in gallery_item_divs:
        if "random-thumb" in item_div.get("class", []):
            continue
        
        gallery_data = extract_gallery_data_from_item(item_div)
        if gallery_data:
            scraped_galleries.append(gallery_data)
            
    return scraped_galleries

# --- END OF NEW HELPER FUNCTIONS ---


def scrape_generic_video_list_page(section: str, page_number: int) -> List[VideoData]:
    """Scrapes lists of videos from pages like /fresh, /best, /trend."""
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")

    if section == "trend":
         scrape_url = f"{BASE_URL}/trend/{page_number}" 
    elif page_number == 1:
         scrape_url = f"{BASE_URL}/{section}/" 
    else:
         scrape_url = f"{BASE_URL}/{section}/{page_number}/" 

    soup = safe_scrape_page(scrape_url)
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')

    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}. No items found?")
        return [] 

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No video items found on {scrape_url}.")
        return [] 

    videos = []
    for item in items:
        if "random-thumb" in item.get("class", []):
            continue

        title_elem = item.find("div", class_="b-thumb-item__title")
        title = title_elem.get_text(strip=True) if title_elem else None
        title_attribute = None 

        duration_elem = item.find("div", class_="b-thumb-item__duration")
        duration_span = duration_elem.find("span") if duration_elem else None
        duration = duration_span.get_text(strip=True) if duration_span else None

        image_urls_data = extract_image_urls(item) 

        link = None
        gallery_id = None
        thumb_id = None
        preview_video_url = None
        link_elem = item.find("a", class_="js-gallery-link") # Primary link for these sections
        if not link_elem: # Fallback if only js-gallery-stats is present on main link
            link_elem = item.find("a", class_="js-gallery-stats")

        if link_elem:
            href = link_elem.get("href")
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            gallery_id = link_elem.get("data-gallery-id")
            thumb_id = link_elem.get("data-thumb-id")
            preview_video_url = link_elem.get("data-preview")
            title_attribute = link_elem.get("title") 

        if not title and title_attribute: # Use title from <a> tag if specific title div is empty/missing
            title = title_attribute

        categories_elem = item.find("div", class_="b-thumb-item__detail")
        tags = []
        if categories_elem:
            tag_links = categories_elem.find_all("a")
            tags = [
                Tag(
                    link=f"{BASE_URL}{link_a['href']}" if link_a.get('href', '').startswith('/') else link_a.get('href'),
                    name=link_a.get_text(strip=True)
                )
                for link_a in tag_links if link_a.get('href') and link_a.get_text(strip=True)
            ]

        if link or title:
             video = VideoData(
                 duration=duration,
                 gallery_id=gallery_id,
                 image_urls=image_urls_data,
                 link=link,
                 preview_video_url=preview_video_url,
                 tags=tags,
                 thumb_id=thumb_id,
                 title=title,
                 title_attribute=title_attribute
             )
             videos.append(video)
        else:
             logger.warning(f"Skipping video item from {scrape_url} due to missing link and title: {item.prettify()[:200]}")
    return videos

def scrape_search_page(search_content: str, page_number: int) -> List[VideoData]:
     """Scrapes search results pages."""
     if page_number <= 0:
         raise HTTPException(status_code=400, detail="Page number must be positive.")
     if not search_content:
         raise HTTPException(status_code=400, detail="Search content cannot be empty.")

     safe_search_content = quote(search_content)
     if page_number == 1:
         scrape_url = f"{BASE_URL}/search/{safe_search_content}/"
     else:
         scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/"

     soup = safe_scrape_page(scrape_url)
     no_results_message = soup.find('div', class_='b-catalog-info-descr')
     if no_results_message and "no results found" in no_results_message.get_text(strip=True).lower():
          logger.info(f"Site reported 'No results found' for '{search_content}' on {scrape_url}")
          return []

     gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
     if not gallery_list_container:
         logger.warning(f"Gallery list container not found on search page {scrape_url}.")
         return [] 

     items = gallery_list_container.find_all('div', class_='b-thumb-item')
     if not items:
         logger.info(f"No video items found on search page {scrape_url}.")
         return []

     videos = [] # Replicate item parsing, similar to scrape_generic_video_list_page
     for item in items:
        if "random-thumb" in item.get("class", []):
            continue

        title_elem = item.find("div", class_="b-thumb-item__title")
        title = title_elem.get_text(strip=True) if title_elem else None
        title_attribute = None

        duration_elem = item.find("div", class_="b-thumb-item__duration")
        duration_span = duration_elem.find("span") if duration_elem else None
        duration = duration_span.get_text(strip=True) if duration_span else None

        image_urls_data = extract_image_urls(item)

        link = None; gallery_id = None; thumb_id = None; preview_video_url = None
        link_elem = item.find("a", class_="js-gallery-link") # Prefer js-gallery-link for search results too
        if not link_elem: link_elem = item.find("a", class_="js-gallery-stats")


        if link_elem:
            href = link_elem.get("href")
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            gallery_id = link_elem.get("data-gallery-id")
            thumb_id = link_elem.get("data-thumb-id")
            preview_video_url = link_elem.get("data-preview")
            title_attribute = link_elem.get("title")

        if not title and title_attribute:
            title = title_attribute

        categories_elem = item.find("div", class_="b-thumb-item__detail")
        tags = []
        if categories_elem:
            tag_links = categories_elem.find_all("a")
            tags = [
                Tag(
                    link=f"{BASE_URL}{link_a['href']}" if link_a.get('href', '').startswith('/') else link_a.get('href'),
                    name=link_a.get_text(strip=True)
                )
                for link_a in tag_links if link_a.get('href') and link_a.get_text(strip=True)
            ]

        if link or title:
             videos.append(VideoData(
                 duration=duration, gallery_id=gallery_id, image_urls=image_urls_data, link=link,
                 preview_video_url=preview_video_url, tags=tags, thumb_id=thumb_id, title=title,
                 title_attribute=title_attribute
             ))
        else:
             logger.warning(f"Skipping search result item from {scrape_url} due to missing link/title: {item.prettify()[:200]}")
     return videos


def scrape_category_list_page(page_number: int) -> List[CategoryData]:
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    scrape_url = f"{BASE_URL}/categories/{page_number}" if page_number > 1 else f"{BASE_URL}/categories/"
    soup = safe_scrape_page(scrape_url)
    category_list_container = soup.find('div', id='galleries', class_='js-category-list')
    if not category_list_container: return []
    items = category_list_container.find_all('div', class_='b-thumb-item--cat')
    if not items: return []
    
    scraped_data = []
    for item_soup in items:
        link_tag = item_soup.find('a', class_='js-category-stats')
        link, category_id, title = None, None, None
        if link_tag:
            href_relative = link_tag.get('href')
            link = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            category_id = link_tag.get('data-category-id')
            title = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        div_text = title_div.get_text(strip=True) if title_div else ""
        if div_text and (not title or len(div_text) > len(title)):
             title = div_text
        
        image_urls = extract_image_urls(item_soup)
        if link and title:
            scraped_data.append(CategoryData(link=link, category_id=category_id, title=title, image_urls=image_urls))
        else:
            logger.warning(f"Skipping category item due to missing data from {scrape_url}: {item_soup.prettify()[:200]}")
    return scraped_data


def scrape_pornstar_list_page(page_number: int) -> List[PornstarData]:
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    scrape_url = f"{BASE_URL}/pornstars/{page_number}/" if page_number > 1 else f"{BASE_URL}/pornstars/"
    soup = safe_scrape_page(scrape_url)
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
    if not pornstar_list_container:
        if soup.find('div', class_='js-gallery-list'): logger.info(f"Found gallery list, not pornstars on {scrape_url}.")
        return []
    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')
    if not items: return []

    scraped_data = []
    for item_soup in items:
        link_tag = item_soup.find('a', class_='js-pornstar-stats')
        link, pornstar_id, name = None, None, None
        if link_tag:
            href_relative = link_tag.get('href')
            link = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            pornstar_id = link_tag.get('data-pornstar-id')
            name = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        div_text = title_div.get_text(strip=True) if title_div else ""
        if div_text and not name : # Only use div title if <a> title was missing
            name = div_text
            
        image_urls = extract_image_urls(item_soup)
        if link and name:
             scraped_data.append(PornstarData(link=link, pornstar_id=pornstar_id, name=name, image_urls=image_urls))
        else:
            logger.warning(f"Skipping pornstar item due to missing data from {scrape_url}: {item_soup.prettify()[:200]}")
    return scraped_data

def scrape_channel_list_page(page_number: int) -> List[ChannelData]:
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    scrape_url = f"{BASE_URL}/channels/{page_number}/" if page_number > 1 else f"{BASE_URL}/channels/"
    soup = safe_scrape_page(scrape_url)
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')
    if not channel_list_container:
        if soup.find('div', class_='js-gallery-list'): logger.info(f"Found gallery list, not channels on {scrape_url}.")
        return []
    items = channel_list_container.find_all('div', class_='b-thumb-item--cat') # Uses --cat class
    if not items: return []

    scraped_data = []
    for item_soup in items:
        link_tag = item_soup.find('a', class_='js-channel-stats')
        link, channel_id, name = None, None, None
        if link_tag:
            href_relative = link_tag.get('href')
            link = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            channel_id = link_tag.get('data-channel-id')
            name = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span')
            span_name = title_span.get_text(strip=True) if title_span else ""
            if span_name and (not name or len(span_name) > len(name)):
                 name = span_name
                 
        image_urls = extract_image_urls(item_soup)
        if link and name:
             scraped_data.append(ChannelData(link=link, channel_id=channel_id, name=name, image_urls=image_urls))
        else:
            logger.warning(f"Skipping channel item due to missing data from {scrape_url}: {item_soup.prettify()[:200]}")
    return scraped_data


def scrape_video_stream_data(video_page_url: str) -> StreamData:
    if not video_page_url or not video_page_url.startswith('http'):
         raise HTTPException(status_code=400, detail=f"Invalid video page URL provided: {video_page_url}")

    soup = safe_scrape_page(video_page_url)
    stream_data = StreamData(video_page_url=video_page_url)

    video_tag = soup.find('video', id='video_html5_api')
    if not video_tag:
        player_div = soup.find('div', class_='b-video-player')
        if player_div: video_tag = player_div.find('video')

    if not video_tag:
        logger.warning(f"Video player tag not found on {video_page_url}.")
        raise HTTPException(status_code=404, detail="Video player tag not found on the page.")

    if video_tag.has_attr('src'):
        stream_data.main_video_src = video_tag['src']

    found_sources = set()
    if stream_data.main_video_src: found_sources.add(stream_data.main_video_src)

    for source_tag in video_tag.find_all('source'):
        src_url = source_tag.get('src')
        if src_url and src_url not in found_sources:
             stream_data.source_tags.append(StreamSource(
                 src=src_url, type=source_tag.get('type'), size=source_tag.get('size')
             ))
             found_sources.add(src_url)

    if not stream_data.main_video_src and not stream_data.source_tags:
        stream_data.note = "No direct video <src> or <source> tags found. Video might be JS loaded."
    if video_tag.has_attr('poster'):
        stream_data.poster_image = video_tag['poster']
    if video_tag.has_attr('data-preview'):
        sprite_string = video_tag['data-preview']
        stream_data.sprite_previews = [s.strip() for s in sprite_string.split(',') if s.strip()]
    return stream_data

# --- API Endpoints ---

@app.get("/")
async def root():
    """Basic info about the API."""
    return {
        "message": "Welcome to the Consolidated HQPORN Scraper API",
        "endpoints": {
            "/docs": "Swagger UI documentation.",
            "/redoc": "ReDoc documentation.",
            "/scrape?url={url_to_scrape}": "GET - Scrape gallery data from a generic URL (new).", # MODIFIED
            "/scrape-videos": "POST - Scrape video data from a generic listing URL (provide URL in request body).",
            "/api/fresh/{page_number}": "GET - Scrape fresh videos by page number.",
            "/api/best/{page_number}": "GET - Scrape best-rated videos by page number.",
            "/api/trend/{page_number}": "GET - Scrape trending videos by page number.",
            "/api/search/{search_content}/{page_number}": "GET - Search for videos by content and page number.",
            "/api/categories/{page_number}": "GET - Scrape categories list by page number.",
            "/api/pornstars/{page_number}": "GET - Scrape pornstars list by page number.",
            "/api/channels/{page_number}": "GET - Scrape channels list by page number.",
            "/api/stream/{video_page_link:path}": "GET - Scrape a specific video page for streaming links.",
        }
    }

# NEW /scrape (GET) ENDPOINT
@app.get("/scrape", response_model=List[VideoData], summary="Scrape Gallery Data by URL")
async def scrape_galleries_from_url(
    url: str = Query(..., description="The full URL of the webpage to scrape (e.g., https://hqporn.xxx/some-listing/). Must start with http:// or https://.")
):
    """
    Scrapes gallery/video data from the provided URL.
    - Fetches content from the given `url`.
    - Looks for `div` elements with class `b-thumb-item`.
    - For each item, it primarily uses an `a` tag with class `js-gallery-stats` to extract most data.
    - The `title` field in the response is a special version: the `title` attribute of the `a.js-gallery-stats` tag, with all whitespace characters removed.
    - The `title_attribute` field stores the original `title` attribute from the `a.js-gallery-stats` tag.
    """
    if not url or not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(
            status_code=400, 
            detail="Invalid URL provided. Must be a full HTTP/HTTPS URL."
        )
    return scrape_url_for_gallery_data(url)


@app.post("/scrape-videos", response_model=List[VideoData], summary="Scrape generic video listing page (POST)")
async def scrape_videos_endpoint(request: ScrapeRequest):
    """
    Scrape video data from the URL provided in the request body.
    This endpoint is general purpose for video listings. It looks for 'div.b-thumb-item.js-thumb-item.js-thumb'
    and extracts data based on common structures found on the site.
    The 'title' is typically the display title, and 'title_attribute' is the hover title.
    """
    logger.info(f"Attempting to scrape videos from generic URL (POST): {request.url}")
    soup = safe_scrape_page(request.url)
    
    # Selector used by original /scrape-videos logic for general video items
    video_items = soup.find_all("div", class_="b-thumb-item js-thumb-item js-thumb") 

    videos = []
    for item in video_items:
        if "random-thumb" in item.get("class", []):
            continue

        title_elem = item.find("div", class_="b-thumb-item__title js-gallery-title")
        if not title_elem: # Fallback to general title class
             title_elem = item.find("div", class_="b-thumb-item__title")
        
        title_from_div = title_elem.get_text(strip=True) if title_elem else None
        
        duration_elem = item.find("div", class_="b-thumb-item__duration")
        duration_span = duration_elem.find("span") if duration_elem else None
        duration = duration_span.get_text(strip=True) if duration_span else None

        image_urls_data = extract_image_urls(item)

        link, gallery_id, thumb_id, preview_video_url, title_attribute_from_link = None, None, None, None, None
        
        # Primary link element for general video items (more specific than just js-gallery-stats)
        link_elem = item.find("a", class_="js-gallery-link js-gallery-stats")
        if not link_elem : # Fallback if the combined class is not present
            link_elem = item.find("a", class_="js-gallery-link")
            if not link_elem:
                 link_elem = item.find("a", class_="js-gallery-stats")


        if link_elem:
            href = link_elem.get("href")
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            gallery_id = link_elem.get("data-gallery-id")
            thumb_id = link_elem.get("data-thumb-id")
            preview_video_url = link_elem.get("data-preview")
            title_attribute_from_link = link_elem.get("title")

        # Determine final title for VideoData.title
        final_title = title_from_div
        if not final_title and title_attribute_from_link: # If div title missing, use link's title attribute
            final_title = title_attribute_from_link

        categories_elem = item.find("div", class_="b-thumb-item__detail")
        tags = []
        if categories_elem:
            tag_links = categories_elem.find_all("a")
            tags = [
                Tag(
                    link=f"{BASE_URL}{link_a['href']}" if link_a.get('href', '').startswith('/') else link_a.get('href'),
                    name=link_a.get_text(strip=True)
                )
                for link_a in tag_links if link_a.get('href') and link_a.get_text(strip=True)
            ]

        if link or final_title:
            videos.append(VideoData(
                duration=duration, gallery_id=gallery_id, image_urls=image_urls_data, link=link,
                preview_video_url=preview_video_url, tags=tags, thumb_id=thumb_id,
                title=final_title, title_attribute=title_attribute_from_link
            ))
        else:
            logger.warning(f"Skipping item from POST /scrape-videos {request.url} due to missing link/title: {item.prettify()[:200]}")

    if not videos:
        if not soup.find('div', id='galleries') and not soup.find_all("div", class_="b-thumb-item"):
            raise HTTPException(status_code=404, detail="The provided URL does not appear to be a recognizable video listing page.")
        else:
             logger.info(f"Scraped {request.url} (POST) but found 0 video items matching criteria.")
             return []
    return videos


@app.get("/api/fresh/{page_number}", response_model=List[VideoData], summary="Get Fresh Videos Page")
async def get_fresh_page(page_number: int = Path(..., description="Page number (>0)", gt=0)):
    return scrape_generic_video_list_page(section="fresh", page_number=page_number)

@app.get("/api/best/{page_number}", response_model=List[VideoData], summary="Get Best Rated Videos Page")
async def get_best_rated_page(page_number: int = Path(..., description="Page number (>0)", gt=0)):
    return scrape_generic_video_list_page(section="best", page_number=page_number)

@app.get("/api/trend/{page_number}", response_model=List[VideoData], summary="Get Trending Videos Page")
async def get_trend_page(page_number: int = Path(..., description="Page number (>0)", gt=0)):
    return scrape_generic_video_list_page(section="trend", page_number=page_number)

@app.get("/api/search/{search_content}/{page_number}", response_model=List[VideoData], summary="Search Videos")
async def get_search_results_page(
    search_content: str = Path(..., description="The search query."),
    page_number: int = Path(..., description="Page number (>0)", gt=0)
):
    if not search_content.strip(): # Check if search content is not just whitespace
        raise HTTPException(status_code=400, detail="Search content cannot be empty or whitespace.")
    return scrape_search_page(search_content=search_content, page_number=page_number)

@app.get("/api/categories/{page_number}", response_model=List[CategoryData], summary="Get Categories Page")
async def get_categories_page(page_number: int = Path(..., description="Page number (>0)", gt=0)):
    return scrape_category_list_page(page_number=page_number)

@app.get("/api/pornstars/{page_number}", response_model=List[PornstarData], summary="Get Pornstars Page")
async def get_pornstars_page(page_number: int = Path(..., description="Page number (>0)", gt=0)):
    return scrape_pornstar_list_page(page_number=page_number)

@app.get("/api/channels/{page_number}", response_model=List[ChannelData], summary="Get Channels Page")
async def get_channels_page(page_number: int = Path(..., description="Page number (>0)", gt=0)):
    return scrape_channel_list_page(page_number=page_number)

@app.get("/api/stream/{video_page_link:path}", response_model=StreamData, summary="Get Stream Links for a Video Page")
async def get_stream_links(
    video_page_link: str = Path(..., description="Full URL of the video page (e.g., https://hqporn.xxx/video-slug.html). Must start with http.")
):
    return scrape_video_stream_data(video_page_url=video_page_link)


# --- Main execution block for running with uvicorn ---
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000)) 
    uvicorn.run(app, host="0.0.0.0", port=port)
