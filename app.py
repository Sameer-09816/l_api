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

class ScrapeRequest(BaseModel):
    url: HttpUrl

class Tag(BaseModel):
    link: str
    name: str

class ImageUrls(BaseModel):
    img_src: Optional[str] = None
    jpeg: Optional[str] = None
    webp: Optional[str] = None

class VideoData(BaseModel):
    duration: Optional[str] = None
    gallery_id: Optional[str] = None
    image_urls: ImageUrls
    link: str
    preview_video_url: Optional[str] = None
    tags: List[Tag]
    thumb_id: Optional[str] = None
    title: str
    title_attribute: Optional[str] = None

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

class CategoryItem(BaseModel):
    link: str
    category_id: Optional[str] = None
    title: str
    image_urls: ImageUrls

class ChannelItem(BaseModel):
    link: str
    channel_id: Optional[str] = None
    name: str
    image_urls: ImageUrls

class PornstarItem(BaseModel):
    link: str
    pornstar_id: Optional[str] = None
    name: str
    image_urls: ImageUrls

class SourceTagItem(BaseModel):
    src: str
    type: Optional[str] = None
    size: Optional[str] = None

class StreamDataItem(BaseModel):
    video_page_url: str
    main_video_src: Optional[str] = None
    source_tags: List[SourceTagItem]
    poster_image: Optional[str] = None
    sprite_previews: List[str]
    note: Optional[str] = None
    error: Optional[str] = None


# --- FastAPI Application Instance ---
# Ensure this file is named main.py and this instance is named 'app'
app = FastAPI(
    title="Unified Scraper API",
    description="An API that combines various web scrapers for video and content metadata.",
    version="1.0.0"
)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

def scrape_videos_generic(url: str) -> List[VideoData]:
    try:
        response = make_request(url, timeout=10)
        if not response:
            # Consider raising specific HTTP Exception if fetch fails right away
            raise HTTPException(status_code=503, detail=f"Failed to fetch webpage for generic scraping: {url}")

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
            jpeg_val = jpeg_source["srcset"] if jpeg_source and "srcset" in jpeg_source.attrs else img_src
            webp_val = webp_source["srcset"] if webp_source and "srcset" in webp_source.attrs else ""

            link_elem = item.find("a", class_="js-gallery-stats js-gallery-link")
            link_href = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""
            link_full = link_href
            if link_href and not link_href.startswith("http"):
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
                    cat_name = cat_link.get_text(strip=True)
                    if cat_href and cat_name:
                        full_cat_link = cat_href
                        if not cat_href.startswith("http"):
                            full_cat_link = f"{BASE_URL_HQPORN}{cat_href}" if cat_href.startswith('/') else f"{BASE_URL_HQPORN}/{cat_href}"
                        tags_list.append(Tag(link=full_cat_link, name=cat_name))
            videos.append(VideoData(
                duration=duration,
                gallery_id=gallery_id,
                image_urls=ImageUrls(img_src=img_src, jpeg=jpeg_val, webp=webp_val),
                link=link_full or "", # Ensure link is not None
                preview_video_url=preview_video_url,
                tags=tags_list,
                thumb_id=thumb_id,
                title=title,
                title_attribute=title_attribute
            ))
        return videos
    except HTTPException: # Re-raise if already an HTTPException (e.g. 503 from make_request)
        raise
    except Exception as e:
        logger.error(f"Error processing generic scrape for {url}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing webpage for generic scrape: {str(e)}")


def _parse_hqporn_video_item(item_soup: BeautifulSoup) -> Optional[GenericVideoListItem]:
    data: Dict[str, Any] = {}
    link_tag = item_soup.find('a', class_='js-gallery-link')
    if not link_tag:
        logger.warning("Item found with no js-gallery-link.")
        return None

    href = link_tag.get('href')
    data['link'] = f"{BASE_URL_HQPORN}{href}" if href and href.startswith('/') else (href or "")
    data['gallery_id'] = link_tag.get('data-gallery-id')
    data['thumb_id'] = link_tag.get('data-thumb-id')
    data['preview_video_url'] = link_tag.get('data-preview')
    data['title_attribute'] = link_tag.get('title')

    title_div = item_soup.find('div', class_='b-thumb-item__title')
    data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else (data.get('title_attribute') or 'N/A')

    image_urls_dict: Dict[str, Optional[str]] = {}
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
    
    try:
        return GenericVideoListItem(**data)
    except Exception as e:
        logger.error(f"Failed to create GenericVideoListItem with data {data}: {e}")
        return None


def _scrape_hqporn_video_list_page(scrape_url: str, page_description: str) -> Optional[List[GenericVideoListItem]]:
    logger.info(f"Attempting to scrape {page_description}: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        no_results_msg_div = soup.find('div', class_='b-catalog-info-descr')
        if no_results_msg_div and "no results found" in no_results_msg_div.get_text(strip=True).lower():
             logger.info(f"No results found message on {page_description} at {scrape_url}")
        else:
            logger.warning(f"Gallery list container (div#galleries.js-gallery-list) not found on {scrape_url} for {page_description}.")
        return []

    items_html = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items_html:
        logger.info(f"No 'b-thumb-item' divs found within gallery list on {scrape_url} for {page_description}.")
        return []

    scraped_data: List[GenericVideoListItem] = []
    for item_soup in items_html:
        parsed_item = _parse_hqporn_video_item(item_soup)
        if parsed_item:
            scraped_data.append(parsed_item)
    return scraped_data


def scrape_video_page_for_streams(video_page_url: str) -> StreamDataItem:
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    response = make_request(video_page_url, timeout=20)
    if not response:
        raise HTTPException(status_code=503, detail=f"Failed to fetch video page {video_page_url} for stream links.")

    soup = BeautifulSoup(response.content, 'html.parser')
    stream_data_dict: Dict[str, Any] = {
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
        logger.warning(f"Video player tag ('video#video_html5_api' or 'div.b-video-player video') not found on {video_page_url}.")
        stream_data_dict["error"] = "Video player tag not found."
        return StreamDataItem(**stream_data_dict)

    current_sources_typed: List[SourceTagItem] = []
    seen_src_urls = set()

    if video_tag.has_attr('src'):
        main_src = video_tag['src']
        stream_data_dict["main_video_src"] = main_src
        if main_src not in seen_src_urls:
            current_sources_typed.append(SourceTagItem(
                src=main_src,
                type=video_tag.get('type', 'video/mp4')
            ))
            seen_src_urls.add(main_src)

    source_tags_html_list = video_tag.find_all('source')
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

def _scrape_generic_hqporn_list_page(
    base_path_segment: str, 
    page_number: int, 
    item_class: str, 
    list_class_js_suffix: str,
    item_model: type,
    link_class_js_suffix: str,
    id_attribute_name: str,
    title_source_attr: str = 'title'
    ) -> Optional[List[Any]]:

    scrape_url = f"{BASE_URL_HQPORN}/{base_path_segment}/"
    if page_number > 1:
        scrape_url += f"{page_number}/"
        
    logger.info(f"Attempting to scrape {base_path_segment} from: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        return None

    soup = BeautifulSoup(response.content, 'html.parser')
    list_container = soup.find('div', id='galleries', class_=f'js-{list_class_js_suffix}-list')
    if not list_container:
        logger.warning(f"{list_class_js_suffix} list container not found on {scrape_url}. Page: {page_number}")
        return []

    items_html = list_container.find_all('div', class_=item_class)
    if not items_html:
        logger.info(f"No '{item_class}' items found on page {page_number} for {base_path_segment}.")
        return []

    scraped_data_list: List[Any] = []
    for item_soup in items_html:
        data_dict: Dict[str, Any] = {}
        link_tag = item_soup.find('a', class_=f'js-{link_class_js_suffix}-stats')
        if not link_tag:
            logger.warning(f"Found an item in {base_path_segment} with no js-{link_class_js_suffix}-stats link.")
            continue

        href_relative = link_tag.get('href')
        data_dict['link'] = f"{BASE_URL_HQPORN}{href_relative}" if href_relative and href_relative.startswith('/') else (href_relative or "")
        data_dict[id_attribute_name] = link_tag.get(f'data-{link_class_js_suffix}-id')
        
        item_name = link_tag.get(title_source_attr, '').strip()
        if not item_name: # Fallback to title div text if link title is empty
            title_div = item_soup.find('div', class_='b-thumb-item__title')
            if title_div:
                # For channels and pornstars, the name is sometimes just in the span
                title_span = title_div.find('span') 
                item_name = (title_span or title_div).get_text(strip=True)
        
        # Use 'name' for PornstarItem and ChannelItem, 'title' for CategoryItem
        if item_model == PornstarItem or item_model == ChannelItem:
            data_dict['name'] = item_name
        else:
            data_dict['title'] = item_name


        image_urls_dict_data: Dict[str, Optional[str]] = {}
        picture_tag = item_soup.find('picture')
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls_dict_data['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls_dict_data['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            if img_tag:
                image_urls_dict_data['img_src'] = img_tag.get('data-src', img_tag.get('src'))
        data_dict['image_urls'] = ImageUrls(**image_urls_dict_data)
        
        if (data_dict.get('name') or data_dict.get('title')) and data_dict.get('link'):
            try:
                scraped_data_list.append(item_model(**data_dict))
            except Exception as e_val:
                logger.error(f"Error creating {item_model.__name__} from data: {data_dict}. Error: {e_val}")
    return scraped_data_list


def scrape_hqporn_search_page(search_content: str, page_number: int) -> Optional[List[GenericVideoListItem]]:
    safe_search_content = quote(search_content)
    scrape_url = f"{BASE_URL_HQPORN}/search/{safe_search_content}/"
    if page_number > 1: # Only add page number if > 1 for search
        scrape_url += f"{page_number}/"
    return _scrape_hqporn_video_list_page(scrape_url, f"search results for '{search_content}' page {page_number}")

def scrape_hqporn_fresh_page(page_number: int) -> Optional[List[GenericVideoListItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/fresh/"
    if page_number > 1: scrape_url += f"{page_number}/"
    return _scrape_hqporn_video_list_page(scrape_url, f"fresh videos page {page_number}")

def scrape_hqporn_channels_page(page_number: int) -> Optional[List[ChannelItem]]:
    return _scrape_generic_hqporn_list_page("channels", page_number, 'b-thumb-item--cat', 'channel', ChannelItem, 'channel', 'channel_id')

def scrape_hqporn_best_page(page_number: int) -> Optional[List[GenericVideoListItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/best/"
    if page_number > 1: scrape_url += f"{page_number}/"
    return _scrape_hqporn_video_list_page(scrape_url, f"best videos page {page_number}")

def scrape_hqporn_categories_page(page_number: int) -> Optional[List[CategoryItem]]:
    return _scrape_generic_hqporn_list_page("categories", page_number, 'b-thumb-item--cat', 'category', CategoryItem, 'category', 'category_id')

def scrape_hqporn_pornstars_page(page_number: int) -> Optional[List[PornstarItem]]:
    return _scrape_generic_hqporn_list_page("pornstars", page_number, 'b-thumb-item--star', 'pornstar', PornstarItem, 'pornstar', 'pornstar_id')

def scrape_hqporn_trend_page(page_number: int) -> Optional[List[GenericVideoListItem]]:
    scrape_url = f"{BASE_URL_HQPORN}/trend/{page_number}" # Trend URL structure from original code
    return _scrape_hqporn_video_list_page(scrape_url, f"trend videos page {page_number}")


# --- API Endpoints ---

@app.get("/")
async def root():
    return {
        "message": "Welcome to the Unified Scraper API",
        "documentation_swagger": "/docs",
        "documentation_redoc": "/redoc",
        "endpoints_info": "See /docs or /redoc for detailed endpoint specifications for each scraper."
    }

@app.post("/scrape-videos", response_model=List[VideoData], tags=["Generic Scraper"])
async def scrape_videos_endpoint(request: ScrapeRequest):
    """
    Scrape video data from any webpage URL that matches a common thumbnail structure.
    The URL must be for a page listing multiple videos.
    """
    try:
        videos = scrape_videos_generic(str(request.url))
        if not videos: # scrape_videos_generic raises on major errors or returns list
            raise HTTPException(status_code=404, detail="No videos found or structure not recognized.")
        return videos
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /scrape-videos for {request.url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred: {str(e)}")


@app.get("/api/stream/{video_page_link:path}", response_model=StreamDataItem, tags=["HQPorner Specific"])
async def get_stream_links(video_page_link: str = Path(..., description="Full URL of the HQPorner video page.", example="https://hqporn.xxx/some-video-title_12345.html")):
    """
    Scrapes a specific HQPorner video page URL for streaming links, poster, and sprites.
    `video_page_link` should be the **full URL**.
    """
    if not video_page_link.startswith("http://") and not video_page_link.startswith("https://"):
        raise HTTPException(status_code=400, detail=f"Invalid video_page_link. Must be a full URL. Received: {video_page_link}")
    
    logger.info(f"Request for stream links: {video_page_link}")
    try:
        data = scrape_video_page_for_streams(video_page_link)
        if data.error and "Video player tag not found" in data.error: # Specific known error
             raise HTTPException(status_code=404, detail=data.error)
        return data 
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in /api/stream for {video_page_link}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected server error scraping stream links: {str(e)}")


async def _handle_list_scrape_request(
    scrape_function: callable, 
    error_context: str,
    *args: Any 
    ) -> List[Any]: 
    try:
        data = scrape_function(*args)
        if data is None: # Scraper function indicated a failure to fetch/parse external site
            raise HTTPException(status_code=503, detail=f"Failed to retrieve data for {error_context}. External site might be unavailable or structure changed.")
        # Empty list is a valid response (e.g., no search results, end of pagination)
        return data
    except HTTPException: # Re-raise if already an HTTPException
        raise
    except Exception as e: # Catch any other unexpected error from the scraper function
        logger.error(f"General error during scraping for {error_context} with args {args}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected server error occurred while scraping {error_context}: {str(e)}")


@app.get("/api/search/{search_content}/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_search_results_page(
    search_content: str = Path(..., min_length=1, description="Search query."),
    page_number: int = Path(..., gt=0, description="Page number.")
):
    """Scrape search results from HQPorner by query and page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_search_page,
        f"HQPorner search: '{search_content}', page: {page_number}",
        search_content, page_number
    )

@app.get("/api/fresh/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_fresh_page(page_number: int = Path(..., gt=0, description="Page number for 'fresh' videos.")):
    """Scrape 'fresh' (newest) videos from HQPorner by page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_fresh_page,
        f"HQPorner fresh videos page: {page_number}",
        page_number
    )

@app.get("/api/channels/{page_number}", response_model=List[ChannelItem], tags=["HQPorner Specific"])
async def get_channels_page(page_number: int = Path(..., gt=0, description="Page number for channels list.")):
    """Scrape channels from HQPorner by page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_channels_page,
        f"HQPorner channels page: {page_number}",
        page_number
    )

@app.get("/api/best/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_best_rated_page(page_number: int = Path(..., gt=0, description="Page number for 'best' (top-rated) videos.")):
    """Scrape 'best' (top-rated) videos from HQPorner by page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_best_page,
        f"HQPorner best videos page: {page_number}",
        page_number
    )

@app.get("/api/categories/{page_number}", response_model=List[CategoryItem], tags=["HQPorner Specific"])
async def get_categories_page(page_number: int = Path(..., gt=0, description="Page number for categories list.")):
    """Scrape categories from HQPorner by page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_categories_page,
        f"HQPorner categories page: {page_number}",
        page_number
    )

@app.get("/api/pornstars/{page_number}", response_model=List[PornstarItem], tags=["HQPorner Specific"])
async def get_pornstars_page(page_number: int = Path(..., gt=0, description="Page number for pornstars list.")):
    """Scrape pornstars from HQPorner by page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_pornstars_page,
        f"HQPorner pornstars page: {page_number}",
        page_number
    )

@app.get("/api/trend/{page_number}", response_model=List[GenericVideoListItem], tags=["HQPorner Specific"])
async def get_trend_page(page_number: int = Path(..., gt=0, description="Page number for 'trending' videos.")):
    """Scrape 'trending' videos from HQPorner by page number."""
    return await _handle_list_scrape_request(
        scrape_hqporn_trend_page,
        f"HQPorner trend videos page: {page_number}",
        page_number
    )

# --- For Render.com Deployment / Local Development ---
if __name__ == "__main__":
    import uvicorn
    # This block is for local development. 
    # Render.com will use the Gunicorn start command from your service settings.
    port = int(os.environ.get("PORT", 8000)) 
    # For local, usually better to set a specific host if you're testing from other devices
    # or within Docker. "0.0.0.0" makes it accessible on your network.
    # "127.0.0.1" or "localhost" for local machine only.
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("app:app", host=host, port=port, reload=True) # Use reload for local dev convenience
