import os
import uuid
import logging
from typing import List, Dict, Optional, Any
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Path, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(asctime)s %(message)s')
logger = logging.getLogger(__name__)

# --- Global Constants ---
BASE_URL_HQPORN = "https://hqporn.xxx"
SCRAPE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# --- Pydantic Models ---

# Models from input_file_0.py (Generic Video Scraper)
class ScrapeRequest(BaseModel):
    url: HttpUrl # Ensure it's a valid URL

class Tag(BaseModel):
    link: str # Can be HttpUrl if always absolute, or str if sometimes relative
    name: str

class ImageUrls(BaseModel):
    img_src: Optional[str] = None
    jpeg: Optional[str] = None
    webp: Optional[str] = None

class VideoData(BaseModel): # Used by original /scrape-videos
    duration: Optional[str] = None
    gallery_id: Optional[str] = None
    image_urls: ImageUrls
    link: str
    preview_video_url: Optional[str] = None
    tags: List[Tag]
    thumb_id: Optional[str] = None
    title: str
    title_attribute: Optional[str] = None # Often same as title

# Model for many hqporn list items (fresh, best, search, trend)
class GenericVideoListItem(BaseModel):
    link: str
    gallery_id: Optional[str] = None
    thumb_id: Optional[str] = None
    preview_video_url: Optional[str] = None
    title_attribute: Optional[str] = None
    title: str
    image_urls: ImageUrls
    duration: Optional[str] = None
    tags: List[Tag]

# Model for Category items (from input_file_6.py)
class CategoryItem(BaseModel):
    link: str
    category_id: Optional[str] = None
    title: str
    image_urls: ImageUrls

# Model for Channel items (from input_file_4.py)
class ChannelItem(BaseModel):
    link: str
    channel_id: Optional[str] = None
    name: str # title is used in the original scraper logic for name here
    image_urls: ImageUrls

# Model for Pornstar items (from input_file_7.py)
class PornstarItem(BaseModel):
    link: str
    pornstar_id: Optional[str] = None
    name: str
    image_urls: ImageUrls

# Models for Stream Link Scraper (from input_file_1.py)
class SourceTagItem(BaseModel):
    src: str
    type: Optional[str] = None
    size: Optional[str] = None # Or int if it's always a number

class StreamDataItem(BaseModel):
    video_page_url: str
    main_video_src: Optional[str] = None
    source_tags: List[SourceTagItem]
    poster_image: Optional[str] = None
    sprite_previews: List[str]
    note: Optional[str] = None
    error: Optional[str] = None # For cases where video tag isn't found


# --- FastAPI Application Instance ---
app = FastAPI(
    title="Unified Scraper API",
    description="An API that combines various web scrapers for video and content metadata.",
    version="1.0.0"
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# --- Helper Function to make HTTP requests ---
def make_request(url: str, timeout: int = 15) -> Optional[requests.Response]:
    try:
        response = requests.get(url, headers=SCRAPE_HEADERS, timeout=timeout)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

# --- Scraping Functions ---

# From input_file_0.py (Generic Video Scraper)
def scrape_videos_generic(url: str) -> List[VideoData]:
    try:
        response = make_request(url, timeout=10)
        if not response:
            raise HTTPException(status_code=500, detail=f"Error fetching webpage: {url}")

        soup = BeautifulSoup(response.text, "html.parser")
        video_items = soup.find_all("div", class_="b-thumb-item js-thumb-item js-thumb")
        videos = []
        for item in video_items:
            if "random-thumb" in item.get("class", []):
                continue

            title_elem = item.find("div", class_="b-thumb-item__title js-gallery-title")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title_attribute = title

            duration_elem = item.find("div", class_="b-thumb-item__duration")
            duration = duration_elem.find("span").get_text(strip=True) if duration_elem and duration_elem.find("span") else "Unknown"

            img_elem = item.find("img")
            img_src = img_elem["src"] if img_elem and "src" in img_elem.attrs else ""
            jpeg_source = item.find("source", type="image/jpeg")
            webp_source = item.find("source", type="image/webp")
            jpeg = jpeg_source["srcset"] if jpeg_source and "srcset" in jpeg_source.attrs else img_src
            webp = webp_source["srcset"] if webp_source and "srcset" in webp_source.attrs else ""

            link_elem = item.find("a", class_="js-gallery-stats js-gallery-link")
            link_href = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""
            link_full = link_href # Assume it could be absolute
            if link_href and not link_href.startswith("http"): # Assuming relative links need hqporn base
                 link_full = f"{BASE_URL_HQPORN}{link_href}" if link_href.startswith('/') else f"{BASE_URL_HQPORN}/{link_href}"


            gallery_id = link_elem["data-gallery-id"] if link_elem and "data-gallery-id" in link_elem.attrs else "Unknown"
            preview_video_url = link_elem["data-preview"] if link_elem and "data-preview" in link_elem.attrs else ""
            thumb_id = link_elem["data-thumb-id"] if link_elem and "data-thumb-id" in link_elem.attrs else "Unknown"

            categories_elem = item.find("div", class_="b-thumb-item__detail")
            tags_list = []
            if categories_elem:
                category_links = categories_elem.find_all("a")
                for cat_link in category_links:
                    cat_href = cat_link.get("href")
                    if cat_href:
                        full_cat_link = cat_href
                        if not cat_href.startswith("http"):
                            full_cat_link = f"{BASE_URL_HQPORN}{cat_href}" if cat_href.startswith('/') else f"{BASE_URL_HQPORN}/{cat_href}"
                        tags_list.append(Tag(
                            link=full_cat_link,
                            name=cat_link.get_text(strip=True)
                        ))


            videos.append(VideoData(
                duration=duration,
                gallery_id=gallery_id,
                image_urls=ImageUrls(img_src=img_src, jpeg=jpeg, webp=webp),
                link=link_full,
                preview_video_url=preview_video_url,
                tags=tags_list,
                thumb_id=thumb_id,
                title=title,
                title_attribute=title_attribute
            ))
        return videos
    except Exception as e:
        logger.error(f"Error processing webpage {url}: {str(e)}")
        # This specific scraper function might need to re-raise or handle differently
        # For now, return empty or let FastAPI handle via HTTPException from endpoint
        raise HTTPException(status_code=500, detail=f"Error processing webpage: {str(e)}")

# Common parser for hqporn video list items
def _parse_hqporn_video_item(item_soup: BeautifulSoup) -> Optional[GenericVideoListItem]:
    data: Dict[str, Any] = {} # Explicitly type data
    link_tag = item_soup.find('a', class_='js-gallery-link')
    if not link_tag:
        logger.warning("Found an item with no js-gallery-link.")
        return None

    href = link_tag.get('href')
    data['link'] = f"{BASE_URL_HQPORN}{href}" if href and href.startswith('/') else href
    data['gallery_id'] = link_tag.get('data-gallery-id')
    data['thumb_id'] = link_tag.get('data-thumb-id')
    data['preview_video_url'] = link_tag.get('data-preview')
    data['title_attribute'] = link_tag.get('title')

    title_div = item_soup.find('div', class_='b-thumb-item__title')
    data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data.get('title_attribute', 'N/A')

    image_urls_dict: Dict[str, Optional[str]] = {} # Explicitly type
    picture_tag = item_soup.find('picture', class_='js-gallery-img')
    if picture_tag:
        source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
        image_urls_dict['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
        source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
        image_urls_dict['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
        img_tag = picture_tag.find('img')
        if img_tag:
            image_urls_dict['img_src'] = img_tag.get('data-src', img_tag.get('src'))
    data['image_urls'] = ImageUrls(**image_urls_dict)

    duration_div = item_soup.find('div', class_='b-thumb-item__duration')
    duration_span = duration_div.find('span') if duration_div else None
    data['duration'] = duration_span.text.strip() if duration_span else None

    tags_list_data = []
    detail_div = item_soup.find('div', class_='b-thumb-item__detail')
    if detail_div:
        for tag_a in detail_div.find_all('a'):
            tag_name = tag_a.text.strip()
            tag_link_relative = tag_a.get('href')
            if tag_name and tag_link_relative:
                tag_link_full = f"{BASE_URL_HQPORN}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                tags_list_data.append(Tag(name=tag_name, link=tag_link_full))
    data['tags'] = tags_list_data
    
    return GenericVideoListItem(**data)


def _scrape_hqporn_video_list_page(scrape_url: str, page_description: str) -> Optional[List[GenericVideoListItem]]:
    logger.info(f"Attempting to scrape {page_description}: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        no_results_msg_div = soup.find('div', class_='b-catalog-info-descr') # For search
        if no_results_msg_div and "no results found" in no_results_msg_div.get_text(strip=True).lower():
             logger.info(f"No results found for {page_description} at {scrape_url}")
        else:
            logger.warning(f"Gallery list container not found on {scrape_url} for {page_description}.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on {scrape_url} for {page_description}.")
        return []

    scraped_data: List[GenericVideoListItem] = [] # Explicitly type
    for item_soup in items:
        parsed_item = _parse_hqporn_video_item(item_soup)
        if parsed_item:
            scraped_data.append(parsed_item)
    return scraped_data


# From input_file_1.py (Stream Link Scraper)
def scrape_video_page_for_streams(video_page_url: str) -> StreamDataItem:
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    response = make_request(video_page_url, timeout=20)
    if not response:
        raise HTTPException(status_code=500, detail=f"Failed to fetch {video_page_url}")

    soup = BeautifulSoup(response.content, 'html.parser')
    stream_data_dict: Dict[str, Any] = { # Explicitly type
        "video_page_url": video_page_url,
        "main_video_src": None,
        "source_tags": [],
        "poster_image": None,
        "sprite_previews": [],
        "note": None,
        "error": None
    }

    video_tag = soup.find('video', id='video_html5_api')
    if not video_tag:
        player_div = soup.find('div', class_='b-video-player')
        if player_div:
            video_tag = player_div.find('video')

    if not video_tag:
        logger.warning(f"Video player tag not found on {video_page_url}.")
        stream_data_dict["error"] = "Video player tag not found."
        return StreamDataItem(**stream_data_dict)

    if video_tag.has_attr('src'):
        stream_data_dict["main_video_src"] = video_tag['src']
        is_in_source_tags = any(
            s_tag.has_attr('src') and s_tag['src'] == video_tag['src'] 
            for s_tag in video_tag.find_all('source')
        )
        if not is_in_source_tags:
            stream_data_dict["source_tags"].append(SourceTagItem(
                src=video_tag['src'],
                type=video_tag.get('type', 'video/mp4')
            ))

    source_tags_html_list = video_tag.find_all('source')
    # Ensure main_video_src if added, is a SourceTagItem, and manage seen_src_urls based on SourceTagItem.src
    current_sources_typed: List[SourceTagItem] = list(stream_data_dict["source_tags"]) # Start with what's already there
    seen_src_urls = {st.src for st in current_sources_typed}


    for source_tag_html in source_tags_html_list:
        if source_tag_html.has_attr('src'):
            src_url = source_tag_html['src']
            if src_url not in seen_src_urls:
                current_sources_typed.append(SourceTagItem(
                    src=src_url,
                    type=source_tag_html.get('type'),
                    size=source_tag_html.get('size')
                ))
                seen_src_urls.add(src_url)
    
    stream_data_dict["source_tags"] = current_sources_typed


    if video_tag.has_attr('poster'):
        stream_data_dict["poster_image"] = video_tag['poster']

    if video_tag.has_attr('data-preview'):
        sprite_string = video_tag['data-preview']
        stream_data_dict["sprite_previews"] = [sprite.strip() for sprite in sprite_string.split(',') if sprite.strip()]
    
    if not stream_data_dict["source_tags"] and not stream_data_dict["main_video_src"]:
        logger.warning(f"No direct video src or source tags found for {video_page_url}.")
        stream_data_dict["note"] = "No direct video <src> or <source> tags found. Video content might be loaded via JavaScript."

    return StreamDataItem(**stream_data_dict)


# From input_file_2.py (Search Scraper)
def scrape_hqporn_search_page(search_content: str, page_number: int) -> Optional[List[GenericVideoListItem]]:
    safe_search_content = quote(search_content)
    scrape_url = f"{BASE_URL_HQPORN}/search/{safe_search_content}/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL_HQPORN}/search/{safe_search_content}/"
    return _scrape_hqporn_video_list_page(scrape_url, f"search results for '{search_content}' page {page_number}")


# From input_file_3.py (Fresh Videos Scraper)
def scrape_hqporn_fresh_page(page_number: int) -> Optional[List[GenericVideoListItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/fresh/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL_HQPORN}/fresh/"
    return _scrape_hqporn_video_list_page(scrape_url, f"fresh videos page {page_number}")


# From input_file_4.py (Channels Scraper)
def scrape_hqporn_channels_page(page_number: int) -> Optional[List[ChannelItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/channels/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL_HQPORN}/channels/"
        
    logger.info(f"Attempting to scrape channels from: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')
    if not channel_list_container:
        logger.warning(f"Channel list container not found on {scrape_url}. Page: {page_number}")
        return []

    items = channel_list_container.find_all('div', class_='b-thumb-item--cat') 
    if not items:
        logger.info(f"No channel items found on page {page_number}.")
        return []

    scraped_data: List[ChannelItem] = [] # Explicitly type
    for item_soup in items:
        data: Dict[str, Any] = {} # Explicitly type
        link_tag = item_soup.find('a', class_='js-channel-stats')
        if not link_tag:
            logger.warning("Found a channel item with no js-channel-stats link.")
            continue

        href_relative = link_tag.get('href')
        data['link'] = f"{BASE_URL_HQPORN}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
        data['channel_id'] = link_tag.get('data-channel-id')
        data['name'] = link_tag.get('title', '').strip() # Primary name

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and not data.get('name'): # Fallback if <a> title empty
            title_span = title_div.find('span')
            if title_span and title_span.get_text(strip=True):
                 data['name'] = title_span.get_text(strip=True)
        
        image_urls_dict: Dict[str, Optional[str]] = {} # Explicitly type
        picture_tag = item_soup.find('picture')
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls_dict['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls_dict['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls_dict['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = ImageUrls(**image_urls_dict)
        
        if data.get('name') and data.get('link'):
            try:
                scraped_data.append(ChannelItem(**data))
            except Exception as e:
                logger.error(f"Error creating ChannelItem from data: {data}. Error: {e}")
    return scraped_data


# From input_file_5.py (Best Videos Scraper)
def scrape_hqporn_best_page(page_number: int) -> Optional[List[GenericVideoListItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/best/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL_HQPORN}/best/"
    return _scrape_hqporn_video_list_page(scrape_url, f"best videos page {page_number}")


# From input_file_6.py (Categories Scraper)
def scrape_hqporn_categories_page(page_number: int) -> Optional[List[CategoryItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/categories/{page_number}/" 
    if page_number == 1:
        scrape_url = f"{BASE_URL_HQPORN}/categories/"
        
    logger.info(f"Attempting to scrape categories from: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    category_list_container = soup.find('div', id='galleries', class_='js-category-list')
    if not category_list_container:
        logger.warning(f"Category list container not found on {scrape_url}. Page: {page_number}")
        return []

    items = category_list_container.find_all('div', class_='b-thumb-item--cat')
    if not items:
        logger.info(f"No category items found on page {page_number}.")
        return []

    scraped_data: List[CategoryItem] = [] # Explicitly type
    for item_soup in items:
        data: Dict[str, Any] = {} # Explicitly type
        link_tag = item_soup.find('a', class_='js-category-stats')
        if not link_tag:
            logger.warning("Found a category item with no js-category-stats link.")
            continue

        href_relative = link_tag.get('href')
        data['link'] = f"{BASE_URL_HQPORN}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
        data['category_id'] = link_tag.get('data-category-id')
        data['title'] = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and not data.get('title') and title_div.get_text(strip=True): # Fallback for title
             data['title'] = title_div.get_text(strip=True)
        
        image_urls_dict: Dict[str, Optional[str]] = {} # Explicitly type
        picture_tag = item_soup.find('picture')
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls_dict['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls_dict['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls_dict['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = ImageUrls(**image_urls_dict)
        
        if data.get('title') and data.get('link'):
            try:
                scraped_data.append(CategoryItem(**data))
            except Exception as e:
                logger.error(f"Error creating CategoryItem from data: {data}. Error: {e}")

    return scraped_data


# From input_file_7.py (Pornstars Scraper)
def scrape_hqporn_pornstars_page(page_number: int) -> Optional[List[PornstarItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/pornstars/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL_HQPORN}/pornstars/"
        
    logger.info(f"Attempting to scrape pornstars from: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
    if not pornstar_list_container:
        logger.warning(f"Pornstar list container not found on {scrape_url}. Page: {page_number}")
        return []

    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')
    if not items:
        logger.info(f"No pornstar items found on page {page_number}.")
        return []

    scraped_data: List[PornstarItem] = [] # Explicitly type
    for item_soup in items:
        data: Dict[str, Any] = {} # Explicitly type
        link_tag = item_soup.find('a', class_='js-pornstar-stats')
        if not link_tag:
            logger.warning("Found a pornstar item with no js-pornstar-stats link.")
            continue
        
        href_relative = link_tag.get('href')
        data['link'] = f"{BASE_URL_HQPORN}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
        data['pornstar_id'] = link_tag.get('data-pornstar-id')
        data['name'] = link_tag.get('title', '').strip() # Primary name

        title_div = item_soup.find('div', class_='b-thumb-item__title') # Fallback
        if title_div and not data.get('name') and title_div.get_text(strip=True):
            data['name'] = title_div.get_text(strip=True)
        
        image_urls_dict: Dict[str, Optional[str]] = {} # Explicitly type
        picture_tag = item_soup.find('picture')
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls_dict['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls_dict['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls_dict['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data['image_urls'] = ImageUrls(**image_urls_dict)

        if data.get('name') and data.get('link'):
            try:
                scraped_data.append(PornstarItem(**data))
            except Exception as e:
                logger.error(f"Error creating PornstarItem from data: {data}. Error: {e}")
    return scraped_data


# From input_file_8.py (Trend Scraper, originally just scraper_api.py)
def scrape_hqporn_trend_page(page_number: int) -> Optional[List[GenericVideoListItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/trend/{page_number}" 
    return _scrape_hqporn_video_list_page(scrape_url, f"trend videos page {page_number}")


# --- API Endpoints ---

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Unified Scraper API",
        "documentation_swagger": "/docs",
        "documentation_redoc": "/redoc",
        "endpoints_info": "See /docs or /redoc for detailed endpoint specifications."
    }

# Endpoint from input_file_0.py
@app.post("/scrape-videos", response_model=List[VideoData], tags=["Generic Scraper"])
async def scrape_videos_endpoint(request: ScrapeRequest):
    """
    Scrape video data from any webpage URL that matches a common thumbnail structure.
    The URL must be for a page listing multiple videos (e.g., a gallery or search results page from various sites).
    """
    try:
        videos = scrape_videos_generic(str(request.url)) # Convert HttpUrl to str for requests
        if not videos:
            raise HTTPException(status_code=404, detail="No videos found on the provided webpage or structure not recognized.")
        return videos
    except HTTPException as e: # Re-raise HTTPExceptions
        raise e
    except Exception as e: # Catch other errors from the scraper
        logger.error(f"Unhandled error in scrape_videos_endpoint for {request.url}: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# Endpoint from input_file_1.py
@app.get("/api/stream/{video_page_link:path}", response_model=StreamDataItem, tags=["HQPorner Specific"])
async def get_stream_links(video_page_link: str = Path(..., description="Full URL of the HQPorner video page to scrape.", example="https://hqporn.xxx/some-video-title_12345.html")):
    """
    Scrapes a specific HQPorner video page URL for streaming links, poster, and sprites.
    The `video_page_link` path parameter should be the **full URL** of the video page.
    """
    if not video_page_link.startswith("http://") and not video_page_link.startswith("https://"):
        raise HTTPException(status_code=400, detail=f"Invalid video_page_link. It must be a full URL (starting with http:// or https://). Received: {video_page_link}")
    
    logger.info(f"Received request for video page link: {video_page_link}")
    
    try:
        data = scrape_video_page_for_streams(video_page_link)
        if data.error and "Video player tag not found" in data.error:
             raise HTTPException(status_code=404, detail=data.error)
        return data 
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in get_stream_links for {video_page_link}: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred while scraping stream links: {str(e)}")

# Helper for list-based endpoints
async def _handle_list_scrape_request(
    scrape_function: callable, 
    error_context: str, # For logging/error messages
    *args: Any # Arguments for the scrape_function
    ) -> List[Any]: 
    
    try:
        data = scrape_function(*args)
    except Exception as e: # Catch any exception from the scraper itself before None check
        logger.error(f"Scraper function failed for {error_context} with args {args}. Error: {e}")
        raise HTTPException(status_code=500, detail=f"Scraping failed for {error_context}. Error: {str(e)}")

    if data is None: 
        raise HTTPException(status_code=503, detail=f"Failed to fetch data for {error_context}. The external site might be down or the request failed.")
    return data

# Endpoint from input_file_2.py
@app.get("/api/search/{search_content}/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_search_results_page(
    search_content: str = Path(..., description="The search query string."),
    page_number: int = Path(..., gt=0, description="Page number of search results.")
):
    """Scrape search results from HQPorner."""
    if not search_content: # Should be caught by Path(...) but good to have
        raise HTTPException(status_code=400, detail="Search content cannot be empty.")
    return await _handle_list_scrape_request(
        scrape_hqporn_search_page,
        f"HQPorner search: '{search_content}', page: {page_number}",
        search_content, page_number
    )

# Endpoint from input_file_3.py
@app.get("/api/fresh/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_fresh_page(page_number: int = Path(..., gt=0, description="Page number for fresh videos.")):
    """Scrape fresh videos from HQPorner."""
    return await _handle_list_scrape_request(
        scrape_hqporn_fresh_page,
        f"HQPorner fresh videos page: {page_number}",
        page_number
    )

# Endpoint from input_file_4.py
@app.get("/api/channels/{page_number}", response_model=List[ChannelItem], tags=["HQPorner Specific"])
async def get_channels_page(page_number: int = Path(..., gt=0, description="Page number for channels list.")):
    """Scrape channels from HQPorner."""
    return await _handle_list_scrape_request(
        scrape_hqporn_channels_page,
        f"HQPorner channels page: {page_number}",
        page_number
    )

# Endpoint from input_file_5.py
@app.get("/api/best/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_best_rated_page(page_number: int = Path(..., gt=0, description="Page number for best-rated videos.")):
    """Scrape best/top-rated videos from HQPorner."""
    return await _handle_list_scrape_request(
        scrape_hqporn_best_page,
        f"HQPorner best videos page: {page_number}",
        page_number
    )

# Endpoint from input_file_6.py
@app.get("/api/categories/{page_number}", response_model=List[CategoryItem], tags=["HQPorner Specific"])
async def get_categories_page(page_number: int = Path(..., gt=0, description="Page number for categories list.")):
    """Scrape categories from HQPorner."""
    return await _handle_list_scrape_request(
        scrape_hqporn_categories_page,
        f"HQPorner categories page: {page_number}",
        page_number
    )

# Endpoint from input_file_7.py
@app.get("/api/pornstars/{page_number}", response_model=List[PornstarItem], tags=["HQPorner Specific"])
async def get_pornstars_page(page_number: int = Path(..., gt=0, description="Page number for pornstars list.")):
    """Scrape pornstars from HQPorner."""
    return await _handle_list_scrape_request(
        scrape_hqporn_pornstars_page,
        f"HQPorner pornstars page: {page_number}",
        page_number
    )

# Endpoint from input_file_8.py
@app.get("/api/trend/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_trend_page(page_number: int = Path(..., gt=0, description="Page number for trending videos.")):
    """Scrape trending videos from HQPorner."""
    return await _handle_list_scrape_request(
        scrape_hqporn_trend_page,
        f"HQPorner trend videos page: {page_number}",
        page_number
    )

# --- For Render.com Deployment / Local Development ---
if __name__ == "__main__":
    import uvicorn
    # This block is for local development. Render will use the Gunicorn start command.
    port = int(os.environ.get("PORT", 8000)) 
    uvicorn.run(app, host="0.0.0.0", port=port)
