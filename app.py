import httpx # Using httpx for async requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query, Path as FastApiPath
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import logging
from urllib.parse import quote as url_quote

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global constants
BASE_URL = "https://hqporn.xxx"
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# --- Pydantic Models ---

class Tag(BaseModel):
    link: Optional[str] = None
    name: Optional[str] = None

class ImageUrls(BaseModel):
    img_src: Optional[str] = None
    jpeg: Optional[str] = None
    webp: Optional[str] = None

class VideoListItem(BaseModel):
    link: Optional[HttpUrl] = None
    gallery_id: Optional[str] = None
    thumb_id: Optional[str] = None
    preview_video_url: Optional[str] = None # Can be relative or full, handle accordingly
    title: Optional[str] = None
    title_attribute: Optional[str] = None
    image_urls: Optional[ImageUrls] = None
    duration: Optional[str] = None
    tags: List[Tag] = []

class SourceTag(BaseModel):
    src: str
    type: Optional[str] = None
    size: Optional[str] = None

class StreamData(BaseModel):
    video_page_url: HttpUrl
    main_video_src: Optional[HttpUrl] = None
    source_tags: List[SourceTag] = []
    poster_image: Optional[HttpUrl] = None
    sprite_previews: List[str] = []
    note: Optional[str] = None
    error: Optional[str] = None

class ChannelListItem(BaseModel):
    link: Optional[HttpUrl] = None
    channel_id: Optional[str] = None
    name: Optional[str] = None
    image_urls: Optional[ImageUrls] = None

class PornstarListItem(BaseModel):
    link: Optional[HttpUrl] = None
    pornstar_id: Optional[str] = None
    name: Optional[str] = None
    image_urls: Optional[ImageUrls] = None

class CategoryListItem(BaseModel):
    link: Optional[HttpUrl] = None
    category_id: Optional[str] = None
    title: Optional[str] = None
    image_urls: Optional[ImageUrls] = None

class ScrapeURLRequest(BaseModel):
    url: HttpUrl


# --- HTTP Request Helper ---

async def fetch_url(url: str) -> Optional[BeautifulSoup]:
    headers = {'User-Agent': USER_AGENT}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=20, follow_redirects=True)
            response.raise_for_status()
        return BeautifulSoup(response.content, 'html.parser')
    except httpx.RequestError as e:
        logger.error(f"Error fetching {url}: {e}")
        raise HTTPException(status_code=503, detail=f"Error fetching external URL: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error {e.response.status_code} for {url}: {e}")
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Content not found at {url}")
        else:
            raise HTTPException(status_code=e.response.status_code, detail=f"HTTP error fetching external URL: {e.response.status_code}")
    return None


# --- Common Parsing Helpers ---

def _parse_image_urls(picture_tag: Optional[BeautifulSoup]) -> ImageUrls:
    image_urls_data = {}
    if picture_tag:
        source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
        image_urls_data['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
        
        source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
        image_urls_data['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
        
        img_tag = picture_tag.find('img')
        if img_tag:
            # Prioritize data-src for lazy-loaded images, fallback to src
            image_urls_data['img_src'] = img_tag.get('data-src', img_tag.get('src'))
    return ImageUrls(**image_urls_data)

def _make_absolute_url(href: Optional[str]) -> Optional[str]:
    if href and href.startswith('/'):
        return f"{BASE_URL}{href}"
    return href

# --- Scraper Core Functions ---

async def scrape_video_thumb_items_from_url(scrape_url: str) -> List[VideoListItem]:
    logger.info(f"Attempting to scrape video thumb items from: {scrape_url}")
    soup = await fetch_url(scrape_url)
    if not soup:
        return []

    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        # Check for "No results found" message, typical for search
        no_results_message = soup.find('div', class_='b-catalog-info-descr')
        if no_results_message and "no results found" in no_results_message.get_text(strip=True).lower():
            logger.info(f"No results found on {scrape_url}.")
        else:
            logger.warning(f"Gallery list container (div#galleries.js-gallery-list) not found on {scrape_url}.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No 'div.b-thumb-item' elements found in gallery container on {scrape_url}.")
        return []

    scraped_data = []
    for item_soup in items:
        # Skip potential ad items or other non-video items if they match 'b-thumb-item'
        if "random-thumb" in item_soup.get("class", []): # As seen in input_file_1.py
            continue

        data = {}
        link_tag = item_soup.find('a', class_='js-gallery-link')
        if not link_tag:
            # Fallback for item structure in input_file_1.py (class 'js-gallery-stats js-gallery-link')
            link_tag = item_soup.find("a", class_="js-gallery-stats")
            if not link_tag or "js-gallery-link" not in link_tag.get("class", []): # Ensure it's still gallery related
                 logger.warning("Found an item with no js-gallery-link or js-gallery-stats. Skipping.")
                 continue


        href = link_tag.get('href')
        data['link'] = _make_absolute_url(href)
        data['gallery_id'] = link_tag.get('data-gallery-id')
        data['thumb_id'] = link_tag.get('data-thumb-id')
        data['preview_video_url'] = link_tag.get('data-preview') # This might be a relative path
        data['title_attribute'] = link_tag.get('title')

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        data['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data.get('title_attribute', 'N/A')

        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        # Fallback for different picture tag structure from input_file_1.py
        if not picture_tag:
             img_elem_parent = item_soup.find("img")
             if img_elem_parent:
                 picture_tag = img_elem_parent.parent if img_elem_parent.parent.name == 'picture' else None
        data['image_urls'] = _parse_image_urls(picture_tag)

        duration_div = item_soup.find('div', class_='b-thumb-item__duration')
        duration_span = duration_div.find('span') if duration_div else None
        data['duration'] = duration_span.text.strip() if duration_span else "Unknown"

        tags_list = []
        detail_div = item_soup.find('div', class_='b-thumb-item__detail')
        if detail_div:
            for tag_a in detail_div.find_all('a'):
                tag_name = tag_a.text.strip()
                tag_link_relative = tag_a.get('href')
                if tag_name and tag_link_relative:
                    tag_link_full = _make_absolute_url(tag_link_relative)
                    tags_list.append(Tag(name=tag_name, link=tag_link_full))
        data['tags'] = tags_list
        
        try:
            video_item = VideoListItem(**data)
            scraped_data.append(video_item)
        except Exception as e:
            logger.error(f"Error parsing video item data: {data}. Error: {e}")
            continue
            
    return scraped_data


async def scrape_video_page_for_streams_core(video_page_url: str) -> StreamData:
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    soup = await fetch_url(video_page_url)
    if not soup:
        # fetch_url would raise HTTPException if soup is None due to error
        # This case might be if fetch_url is changed to return None on non-fatal error
        raise HTTPException(status_code=500, detail="Failed to fetch HTML content for stream scraping.")

    stream_data_dict: Dict[str, Any] = { # Type hint for clarity
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
        stream_data_dict["error"] = "Video player tag not found."
        return StreamData(**stream_data_dict)

    if video_tag.has_attr('src'):
        src_val = _make_absolute_url(video_tag['src'])
        stream_data_dict["main_video_src"] = src_val
        # Add to sources list as well if not already covered by <source> tags and unique
        # This logic needs careful checking against actual sources
        current_source_srcs = [s.get('src') for s in video_tag.find_all('source') if s.has_attr('src')]
        if src_val and src_val not in current_source_srcs:
             stream_data_dict["source_tags"].append({
                 "src": src_val, 
                 "type": video_tag.get('type', 'video/mp4') 
             })

    source_tags_html = video_tag.find_all('source')
    found_sources_set = set() 
    if stream_data_dict["main_video_src"]:
        found_sources_set.add(stream_data_dict["main_video_src"])

    for source_tag_html in source_tags_html:
        if source_tag_html.has_attr('src'):
            src_url = _make_absolute_url(source_tag_html['src'])
            if src_url and src_url not in found_sources_set: # Check src_url not None
                stream_data_dict["source_tags"].append({
                    "src": src_url,
                    "type": source_tag_html.get('type'),
                    "size": source_tag_html.get('size') 
                })
                found_sources_set.add(src_url)
    
    unique_sources_final = []
    seen_src_urls_final = set()
    for src_item_dict in stream_data_dict["source_tags"]:
        if src_item_dict['src'] not in seen_src_urls_final:
            unique_sources_final.append(SourceTag(**src_item_dict)) # Convert dict to Pydantic model here
            seen_src_urls_final.add(src_item_dict['src'])
    stream_data_dict["source_tags"] = unique_sources_final # Now a list of SourceTag models

    if video_tag.has_attr('poster'):
        stream_data_dict["poster_image"] = _make_absolute_url(video_tag['poster'])

    if video_tag.has_attr('data-preview'):
        sprite_string = video_tag['data-preview']
        stream_data_dict["sprite_previews"] = [_make_absolute_url(sprite.strip()) for sprite in sprite_string.split(',') if sprite.strip()]
    
    if not stream_data_dict["source_tags"] and not stream_data_dict["main_video_src"]:
        logger.warning(f"No direct video src or source tags found for video on {video_page_url}.")
        stream_data_dict["note"] = "No direct video <src> or <source> tags found. Video content might be loaded via JavaScript variables not parsed by this basic scraper."

    return StreamData(**stream_data_dict)


async def scrape_categories_core(scrape_url: str) -> List[CategoryListItem]:
    logger.info(f"Attempting to scrape categories from: {scrape_url}")
    soup = await fetch_url(scrape_url)
    if not soup: return []

    category_list_container = soup.find('div', id='galleries', class_='js-category-list')
    if not category_list_container:
        logger.warning(f"Category list container ('js-category-list') not found on {scrape_url}.")
        if soup.find('div', class_='js-gallery-list'): # Check for gallery list (end of pagination for categories)
             logger.info(f"Found a video list instead of categories on {scrape_url}. Likely end of category pagination.")
        return []

    items = category_list_container.find_all('div', class_='b-thumb-item--cat')
    if not items:
        logger.info(f"No category items ('b-thumb-item--cat') found on {scrape_url}.")
        return []

    scraped_data = []
    for item_soup in items:
        data: Dict[str, Any] = {}
        link_tag = item_soup.find('a', class_='js-category-stats')
        if not link_tag:
            logger.warning("Found a category item with no js-category-stats link. Skipping.")
            continue
            
        data['link'] = _make_absolute_url(link_tag.get('href'))
        data['category_id'] = link_tag.get('data-category-id')
        data['title'] = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True) and not data.get('title'):
            data['title'] = title_div.get_text(strip=True)
        
        data['image_urls'] = _parse_image_urls(item_soup.find('picture'))
        
        if data.get('title') and data.get('link'):
            try:
                scraped_data.append(CategoryListItem(**data))
            except Exception as e:
                logger.error(f"Error parsing category item data: {data}. Error: {e}")
        else:
            logger.warning(f"Skipping category item due to missing title or link: {item_soup.name}")
    return scraped_data


async def scrape_pornstars_core(scrape_url: str) -> List[PornstarListItem]:
    logger.info(f"Attempting to scrape pornstars from: {scrape_url}")
    soup = await fetch_url(scrape_url)
    if not soup: return []

    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
    if not pornstar_list_container:
        logger.warning(f"Pornstar list container ('js-pornstar-list') not found on {scrape_url}.")
        if soup.find('div', class_='js-gallery-list'):
             logger.info(f"Found a video list instead of pornstars on {scrape_url}. Likely end of pornstar pagination.")
        return []

    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')
    if not items:
        logger.info(f"No pornstar items ('b-thumb-item--star') found on {scrape_url}.")
        return []
    
    scraped_data = []
    for item_soup in items:
        data: Dict[str, Any] = {}
        link_tag = item_soup.find('a', class_='js-pornstar-stats')
        if not link_tag:
            logger.warning("Found a pornstar item with no js-pornstar-stats link. Skipping.")
            continue

        data['link'] = _make_absolute_url(link_tag.get('href'))
        data['pornstar_id'] = link_tag.get('data-pornstar-id')
        data['name'] = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True) and not data.get('name'):
            data['name'] = title_div.get_text(strip=True)

        data['image_urls'] = _parse_image_urls(item_soup.find('picture'))
        
        if data.get('name') and data.get('link'):
            try:
                scraped_data.append(PornstarListItem(**data))
            except Exception as e:
                logger.error(f"Error parsing pornstar item data: {data}. Error: {e}")
        else:
            logger.warning(f"Skipping pornstar item due to missing name or link.")
    return scraped_data


async def scrape_channels_core(scrape_url: str) -> List[ChannelListItem]:
    logger.info(f"Attempting to scrape channels from: {scrape_url}")
    soup = await fetch_url(scrape_url)
    if not soup: return []

    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')
    if not channel_list_container:
        logger.warning(f"Channel list container ('js-channel-list') not found on {scrape_url}.")
        if soup.find('div', class_='js-gallery-list'):
             logger.info(f"Found a gallery list instead of channels on {scrape_url}. Likely end of channel pagination.")
        return []

    items = channel_list_container.find_all('div', class_='b-thumb-item--cat') # Uses 'b-thumb-item--cat' like categories
    if not items:
        logger.info(f"No channel items ('b-thumb-item--cat' within 'js-channel-list') found on {scrape_url}.")
        return []

    scraped_data = []
    for item_soup in items:
        data: Dict[str, Any] = {}
        link_tag = item_soup.find('a', class_='js-channel-stats')
        if not link_tag:
            logger.warning("Found a channel item with no js-channel-stats link. Skipping.")
            continue
        
        data['link'] = _make_absolute_url(link_tag.get('href'))
        data['channel_id'] = link_tag.get('data-channel-id')
        data['name'] = link_tag.get('title', '').strip()

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span')
            if title_span and title_span.get_text(strip=True) and not data.get('name'):
                 data['name'] = title_span.get_text(strip=True)
        
        data['image_urls'] = _parse_image_urls(item_soup.find('picture'))

        if data.get('name') and data.get('link'):
            try:
                scraped_data.append(ChannelListItem(**data))
            except Exception as e:
                logger.error(f"Error parsing channel item data: {data}. Error: {e}")
        else:
            logger.warning(f"Skipping channel item due to missing name or link.")
    return scraped_data


# --- FastAPI App and Endpoints ---
app = FastAPI(title="Unified Scraper API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/", summary="API Root", description="Provides basic information about the API.")
async def root():
    return {
        "message": "Welcome to the Unified Scraper API",
        "documentation_urls": ["/docs", "/redoc"],
        "base_target_url": BASE_URL
    }

# Endpoint from input_file_0.py (stream_link_scraper_api.py)
@app.get("/api/stream/{video_page_link:path}", response_model=StreamData, summary="Scrape Stream Links from Video Page")
async def get_stream_links(video_page_link: HttpUrl = FastApiPath(..., description="Full URL of the video page to scrape.")):
    """
    Scrapes a specific video page URL for direct streaming links, poster image, and sprite previews.
    The `video_page_link` must be a complete URL.
    Example: `/api/stream/https://hqporn.xxx/your-video-path.html`
    """
    # FastAPI with HttpUrl type already validates and parses the URL.
    logger.info(f"Received request for video page link: {video_page_link}")
    
    # Ensure the passed URL is a string for the scraping function
    data = await scrape_video_page_for_streams_core(str(video_page_link)) 
    
    if data.error and data.error == "Video player tag not found.":
        raise HTTPException(status_code=404, detail=data.error)
    if not data.main_video_src and not data.source_tags and not data.error: # if no streams and no specific error
        # this can happen if page is valid but no streams found, maybe not a 404
        logger.warning(f"No stream data found for {video_page_link}, but page parsed.")

    return data

# Endpoint from input_file_1.py (FastAPI general scraper)
@app.post("/api/scrape-videos", response_model=List[VideoListItem], summary="Scrape Video Thumbnails from Custom URL")
async def scrape_videos_from_custom_url_endpoint(request: ScrapeURLRequest):
    """
    Scrapes video thumbnail data from the provided URL. 
    The URL should point to a page listing video thumbnails in a format similar to hqporn.xxx category/search pages.
    """
    videos = await scrape_video_thumb_items_from_url(str(request.url))
    if not videos:
        # fetch_url or scrape_video_thumb_items_from_url will raise HTTPException on errors.
        # If it returns empty list without error, it means no items were found, or page was empty.
        # Let's return 404 specifically if no items, implying nothing scrapable at that URL's content structure.
        raise HTTPException(status_code=404, detail="No video items found or gallery container missing on the provided webpage. Ensure URL points to a compatible listing page.")
    return videos

# Endpoint from input_file_2.py (fresh_videos_scraper_api.py)
@app.get("/api/fresh/{page_number}", response_model=List[VideoListItem], summary="Scrape 'Fresh' Video Listings")
async def get_fresh_videos(page_number: int = FastApiPath(..., gt=0, description="Page number for 'fresh' videos.")):
    scrape_url = f"{BASE_URL}/fresh/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/fresh/"
    return await scrape_video_thumb_items_from_url(scrape_url)

# Endpoint from input_file_3.py (best_videos_scraper_api.py)
@app.get("/api/best/{page_number}", response_model=List[VideoListItem], summary="Scrape 'Best Rated' Video Listings")
async def get_best_rated_videos(page_number: int = FastApiPath(..., gt=0, description="Page number for 'best rated' videos.")):
    scrape_url = f"{BASE_URL}/best/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/best/"
    return await scrape_video_thumb_items_from_url(scrape_url)

# Endpoint from input_file_8.py (scraper_api.py for "trend")
@app.get("/api/trend/{page_number}", response_model=List[VideoListItem], summary="Scrape 'Trending' Video Listings")
async def get_trending_videos(page_number: int = FastApiPath(..., gt=0, description="Page number for 'trending' videos.")):
    scrape_url = f"{BASE_URL}/trend/{page_number}" # original logic didn't use trailing slash or special case page 1
    return await scrape_video_thumb_items_from_url(scrape_url)

# Endpoint from input_file_4.py (search_scraper_api.py)
@app.get("/api/search/{search_content}/{page_number}", response_model=List[VideoListItem], summary="Scrape Search Results for Videos")
async def get_search_results(
    search_content: str = FastApiPath(..., description="Search query term(s)."),
    page_number: int = FastApiPath(..., gt=0, description="Page number for search results.")
):
    safe_search_content = url_quote(search_content)
    scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/search/{safe_search_content}/"
    return await scrape_video_thumb_items_from_url(scrape_url)

# Endpoint from input_file_7.py (category_scraper_api.py)
@app.get("/api/categories/{page_number}", response_model=List[CategoryListItem], summary="Scrape Categories Listings")
async def get_categories_list(page_number: int = FastApiPath(..., gt=0, description="Page number for categories.")):
    scrape_url = f"{BASE_URL}/categories/{page_number}/" # Ensuring trailing slash consistency
    if page_number == 1:
        scrape_url = f"{BASE_URL}/categories/"
    return await scrape_categories_core(scrape_url)


# Endpoint from input_file_6.py (pornstar_scraper_api.py)
@app.get("/api/pornstars/{page_number}", response_model=List[PornstarListItem], summary="Scrape Pornstar Listings")
async def get_pornstars_list(page_number: int = FastApiPath(..., gt=0, description="Page number for pornstars.")):
    scrape_url = f"{BASE_URL}/pornstars/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/pornstars/"
    return await scrape_pornstars_core(scrape_url)

# Endpoint from input_file_5.py (channel_scraper_api.py)
@app.get("/api/channels/{page_number}", response_model=List[ChannelListItem], summary="Scrape Channel Listings")
async def get_channels_list(page_number: int = FastApiPath(..., gt=0, description="Page number for channels.")):
    scrape_url = f"{BASE_URL}/channels/{page_number}/"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/channels/"
    return await scrape_channels_core(scrape_url)


if __name__ == "__main__":
    import uvicorn
    import os
    # For Render.com, it typically sets the PORT environment variable.
    # Default to 8000 if not set, which is a common dev port.
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True) # reload=True for dev
