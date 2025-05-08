# main.py
import logging
from typing import List, Dict, Optional
from urllib.parse import quote, unquote

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://hqporn.xxx"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
HTTP_TIMEOUT = 15  # seconds

app = FastAPI(
    title="Unified Scraper API",
    version="1.0.0",
    description="A collection of scrapers for hqporn.xxx, merged into a single API.",
    redoc_url="/api/redoc",
    docs_url="/api/docs"
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---

class Tag(BaseModel):
    link: str
    name: str

class ImageUrls(BaseModel):
    img_src: Optional[str] = None
    jpeg: Optional[str] = None
    webp: Optional[str] = None

# Model for /api/scrape-videos endpoint (from original input_file_0.py)
class ScrapeRequest(BaseModel):
    url: HttpUrl

class VideoData(BaseModel):
    duration: Optional[str] = None
    gallery_id: Optional[str] = None
    image_urls: Optional[ImageUrls] = None
    link: Optional[str] = None
    preview_video_url: Optional[str] = None
    tags: List[Tag] = []
    thumb_id: Optional[str] = None
    title: Optional[str] = None
    title_attribute: Optional[str] = None

# Common Video List Item for trend, fresh, best, search results
class GenericVideoListItem(BaseModel):
    link: Optional[str] = None
    gallery_id: Optional[str] = None
    thumb_id: Optional[str] = None
    preview_video_url: Optional[str] = None
    title_attribute: Optional[str] = None
    title: Optional[str] = None
    image_urls: Optional[ImageUrls] = None
    duration: Optional[str] = None
    tags: List[Tag] = []

class CategoryListItem(BaseModel):
    link: Optional[str] = None
    category_id: Optional[str] = None
    title: Optional[str] = None
    image_urls: Optional[ImageUrls] = None

class ChannelListItem(BaseModel):
    link: Optional[str] = None
    channel_id: Optional[str] = None
    name: Optional[str] = None
    image_urls: Optional[ImageUrls] = None

class PornstarListItem(BaseModel):
    link: Optional[str] = None
    pornstar_id: Optional[str] = None
    name: Optional[str] = None
    image_urls: Optional[ImageUrls] = None

class SourceTag(BaseModel):
    src: str
    type: Optional[str] = None
    size: Optional[str] = None

class StreamData(BaseModel):
    video_page_url: str
    main_video_src: Optional[str] = None
    source_tags: List[SourceTag] = []
    poster_image: Optional[str] = None
    sprite_previews: List[str] = []
    note: Optional[str] = None

# --- Helper function to make HTTP requests ---
def make_request(url: str) -> Optional[requests.Response]:
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return response
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        return None

# --- Scraping Functions ---

def scrape_videos_from_url(url: str) -> List[VideoData]:
    """Scrapes video data from a generic URL, based on input_file_0.py logic."""
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(url, headers=headers, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        video_items_soup = soup.find_all("div", class_="b-thumb-item js-thumb-item js-thumb")
        
        videos_data = []
        for item_s in video_items_soup:
            if "random-thumb" in item_s.get("class", []):
                continue

            title_elem = item_s.find("div", class_="b-thumb-item__title js-gallery-title")
            title = title_elem.get_text(strip=True) if title_elem else "Unknown"
            title_attribute = title  # Assuming same as title

            duration_elem = item_s.find("div", class_="b-thumb-item__duration")
            duration = duration_elem.find("span").get_text(strip=True) if duration_elem and duration_elem.find("span") else "Unknown"

            img_elem = item_s.find("img")
            img_src = img_elem["src"] if img_elem and "src" in img_elem.attrs else ""
            jpeg_source = item_s.find("source", type="image/jpeg")
            webp_source = item_s.find("source", type="image/webp")
            jpeg = jpeg_source["srcset"] if jpeg_source and "srcset" in jpeg_source.attrs else img_src
            webp = webp_source["srcset"] if webp_source and "srcset" in webp_source.attrs else ""
            
            image_urls_obj = ImageUrls(img_src=img_src, jpeg=jpeg, webp=webp)

            link_elem = item_s.find("a", class_="js-gallery-stats js-gallery-link")
            link_href = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""
            if link_href and not link_href.startswith("http"):
                link_href = f"{BASE_URL}{link_href}"
            
            gallery_id = link_elem["data-gallery-id"] if link_elem and "data-gallery-id" in link_elem.attrs else "Unknown"
            preview_video_url = link_elem["data-preview"] if link_elem and "data-preview" in link_elem.attrs else ""
            thumb_id = link_elem["data-thumb-id"] if link_elem and "data-thumb-id" in link_elem.attrs else "Unknown"

            categories_elem = item_s.find("div", class_="b-thumb-item__detail")
            tags_list = []
            if categories_elem:
                category_links = categories_elem.find_all("a")
                for cat_link in category_links:
                    tag_href = cat_link["href"]
                    full_tag_link = tag_href if tag_href.startswith("http") else f"{BASE_URL}{tag_href}"
                    tags_list.append(Tag(link=full_tag_link, name=cat_link.get_text(strip=True)))

            videos_data.append(VideoData(
                duration=duration, gallery_id=gallery_id, image_urls=image_urls_obj,
                link=link_href, preview_video_url=preview_video_url, tags=tags_list,
                thumb_id=thumb_id, title=title, title_attribute=title_attribute
            ))
        return videos_data
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=503, detail=f"Error fetching webpage: {str(e)}")
    except Exception as e:
        logger.error(f"Error processing webpage ({url}): {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error processing webpage: {str(e)}")

def _parse_common_video_list_item(item_soup: BeautifulSoup) -> Optional[GenericVideoListItem]:
    """Helper to parse a standard video item from a list page."""
    data_dict = {}
    link_tag = item_soup.find('a', class_='js-gallery-link')
    if not link_tag:
        logger.warning("Item missing 'js-gallery-link', skipping.")
        return None

    href = link_tag.get('href')
    data_dict['link'] = f"{BASE_URL}{href}" if href and href.startswith('/') else href
    data_dict['gallery_id'] = link_tag.get('data-gallery-id')
    data_dict['thumb_id'] = link_tag.get('data-thumb-id')
    data_dict['preview_video_url'] = link_tag.get('data-preview')
    data_dict['title_attribute'] = link_tag.get('title')

    title_div = item_soup.find('div', class_='b-thumb-item__title')
    data_dict['title'] = title_div.get_text(separator=' ', strip=True) if title_div else data_dict.get('title_attribute')

    picture_tag = item_soup.find('picture', class_='js-gallery-img')
    image_urls_data = {}
    if picture_tag:
        source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
        image_urls_data['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
        source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
        image_urls_data['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
        img_tag = picture_tag.find('img')
        if img_tag:
            image_urls_data['img_src'] = img_tag.get('data-src', img_tag.get('src'))
    data_dict['image_urls'] = ImageUrls(**image_urls_data) if any(image_urls_data.values()) else None

    duration_div = item_soup.find('div', class_='b-thumb-item__duration')
    duration_span = duration_div.find('span') if duration_div else None
    data_dict['duration'] = duration_span.text.strip() if duration_span else None

    detail_div = item_soup.find('div', class_='b-thumb-item__detail')
    tags_list_data = []
    if detail_div:
        for tag_a in detail_div.find_all('a'):
            tag_name = tag_a.text.strip()
            tag_link_relative = tag_a.get('href')
            if tag_name and tag_link_relative:
                tag_link_full = f"{BASE_URL}{tag_link_relative}" if tag_link_relative.startswith('/') else tag_link_relative
                tags_list_data.append(Tag(name=tag_name, link=tag_link_full))
    data_dict['tags'] = tags_list_data
    
    return GenericVideoListItem(**data_dict)

def scrape_hqporn_video_list_page(scrape_url: str) -> List[GenericVideoListItem]:
    """Generic scraper for pages listing videos (trend, fresh, best, search)."""
    logger.info(f"Attempting to scrape video list from: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        raise HTTPException(status_code=503, detail=f"Failed to fetch content from {scrape_url}.")

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    
    if not gallery_list_container:
        # Check for specific "no results found" message if applicable (e.g., from search)
        no_results_msg = soup.find('div', class_='b-catalog-info-descr') # Common for such messages
        if no_results_msg and "no results found" in no_results_msg.get_text(strip=True).lower():
            logger.info(f"No results found on {scrape_url}")
            return []
        logger.warning(f"Gallery list container not found on {scrape_url}.")
        return []

    items_soup = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items_soup:
        logger.info(f"No video items found in gallery container on {scrape_url}.")
        return []

    scraped_data = [item for item_s in items_soup if (item := _parse_common_video_list_item(item_s)) is not None]
    return scraped_data

def _parse_category_list_item(item_soup: BeautifulSoup) -> Optional[CategoryListItem]:
    data_dict = {}
    link_tag = item_soup.find('a', class_='js-category-stats')
    if not link_tag: return None
    
    href_relative = link_tag.get('href')
    data_dict['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
    data_dict['category_id'] = link_tag.get('data-category-id')
    data_dict['title'] = link_tag.get('title', '').strip()

    if not data_dict['title']: # Fallback title
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div: data_dict['title'] = title_div.get_text(strip=True)

    picture_tag = item_soup.find('picture')
    img_data = {}
    if picture_tag:
        img_data['webp'] = (sp := picture_tag.find('source', attrs={'type': 'image/webp'})) and sp.get('srcset')
        img_data['jpeg'] = (sp := picture_tag.find('source', attrs={'type': 'image/jpeg'})) and sp.get('srcset')
        img_data['img_src'] = (img := picture_tag.find('img')) and img.get('data-src', img.get('src'))
    data_dict['image_urls'] = ImageUrls(**img_data) if any(img_data.values()) else None
    
    return CategoryListItem(**data_dict) if data_dict.get('title') and data_dict.get('link') else None

def _parse_pornstar_list_item(item_soup: BeautifulSoup) -> Optional[PornstarListItem]:
    data_dict = {}
    link_tag = item_soup.find('a', class_='js-pornstar-stats')
    if not link_tag: return None

    href_relative = link_tag.get('href')
    data_dict['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
    data_dict['pornstar_id'] = link_tag.get('data-pornstar-id')
    data_dict['name'] = link_tag.get('title', '').strip()

    if not data_dict['name']: # Fallback name
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div: data_dict['name'] = title_div.get_text(strip=True)

    picture_tag = item_soup.find('picture')
    img_data = {}
    if picture_tag: # Identical image parsing logic
        img_data['webp'] = (sp := picture_tag.find('source', attrs={'type': 'image/webp'})) and sp.get('srcset')
        img_data['jpeg'] = (sp := picture_tag.find('source', attrs={'type': 'image/jpeg'})) and sp.get('srcset')
        img_data['img_src'] = (img := picture_tag.find('img')) and img.get('data-src', img.get('src'))
    data_dict['image_urls'] = ImageUrls(**img_data) if any(img_data.values()) else None

    return PornstarListItem(**data_dict) if data_dict.get('name') and data_dict.get('link') else None

def _parse_channel_list_item(item_soup: BeautifulSoup) -> Optional[ChannelListItem]:
    data_dict = {}
    link_tag = item_soup.find('a', class_='js-channel-stats')
    if not link_tag: return None

    href_relative = link_tag.get('href')
    data_dict['link'] = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
    data_dict['channel_id'] = link_tag.get('data-channel-id')
    data_dict['name'] = link_tag.get('title', '').strip() # Name from <a> title

    if not data_dict['name']: # Fallback name often in a span within title div
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and (title_span := title_div.find('span')):
            data_dict['name'] = title_span.get_text(strip=True)
    
    picture_tag = item_soup.find('picture')
    img_data = {} # Identical image parsing logic
    if picture_tag:
        img_data['webp'] = (sp := picture_tag.find('source', attrs={'type': 'image/webp'})) and sp.get('srcset')
        img_data['jpeg'] = (sp := picture_tag.find('source', attrs={'type': 'image/jpeg'})) and sp.get('srcset')
        img_data['img_src'] = (img := picture_tag.find('img')) and img.get('data-src', img.get('src'))
    data_dict['image_urls'] = ImageUrls(**img_data) if any(img_data.values()) else None

    return ChannelListItem(**data_dict) if data_dict.get('name') and data_dict.get('link') else None

def scrape_list_page_generic(scrape_url: str, container_sel: tuple, item_sel: tuple, parser_func, list_type: str) -> list:
    logger.info(f"Attempting to scrape {list_type} from: {scrape_url}")
    response = make_request(scrape_url)
    if not response:
        raise HTTPException(status_code=503, detail=f"Failed to fetch {list_type} from {scrape_url}.")

    soup = BeautifulSoup(response.content, 'html.parser')
    list_container = soup.find(container_sel[0], container_sel[1])
    
    if not list_container:
        # Check if a generic gallery list exists where the specific list was expected (end of specific pagination?)
        if soup.find('div', class_='js-gallery-list') and not soup.find(container_sel[0], class_=container_sel[1].get('class')):
             logger.warning(f"Found generic gallery list instead of {list_type} on {scrape_url}. Likely end of {list_type} pagination.")
        else:
            logger.warning(f"{list_type.capitalize()} list container ({container_sel}) not found on {scrape_url}.")
        return []

    items_soup = list_container.find_all(item_sel[0], item_sel[1])
    if not items_soup:
        logger.info(f"No {list_type} items found using {item_sel} in container on {scrape_url}.")
        return []

    return [item for item_s in items_soup if (item := parser_func(item_s)) is not None]

def scrape_video_page_for_streams(video_page_url: str) -> StreamData:
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    response = make_request(video_page_url)
    if not response:
        raise HTTPException(status_code=503, detail=f"Failed to fetch video page {video_page_url}")

    soup = BeautifulSoup(response.content, 'html.parser')
    
    stream_data = {"video_page_url": video_page_url, "source_tags": [], "sprite_previews": []}
    video_tag = soup.find('video', id='video_html5_api') or \
                (soup.find('div', class_='b-video-player') and soup.find('div', class_='b-video-player').find('video'))

    if not video_tag:
        stream_data["note"] = "Video player tag not found."
        return StreamData(**stream_data)

    if video_tag.has_attr('src'):
        stream_data["main_video_src"] = video_tag['src']
        # Add to source_tags if unique
        if not any(st.src == video_tag['src'] for st in stream_data["source_tags"] if isinstance(st, SourceTag)):
             stream_data["source_tags"].append(SourceTag(src=video_tag['src'], type=video_tag.get('type', 'video/mp4')))

    processed_srcs = {st.src for st in stream_data["source_tags"] if isinstance(st, SourceTag)}
    for source_s in video_tag.find_all('source'):
        if source_s.has_attr('src') and source_s['src'] not in processed_srcs:
            stream_data["source_tags"].append(SourceTag(
                src=source_s['src'],
                type=source_s.get('type'),
                size=source_s.get('size')
            ))
            processed_srcs.add(source_s['src'])
    
    if video_tag.has_attr('poster'): stream_data["poster_image"] = video_tag['poster']
    if video_tag.has_attr('data-preview'):
        sprites = video_tag['data-preview']
        stream_data["sprite_previews"] = [s.strip() for s in sprites.split(',') if s.strip()]
    
    if not stream_data.get("main_video_src") and not stream_data["source_tags"]:
        stream_data["note"] = "No direct video <src> or <source> tags found. Video might be loaded via JS."

    return StreamData(**stream_data)


# --- API Endpoints ---

@app.get("/", tags=["General"])
async def root_info():
    return {
        "message": "Welcome to the Unified Scraper API",
        "documentation_urls": {"swagger_ui": app.docs_url, "redoc": app.redoc_url},
        "repository": "https://github.com/your-repo/scraper-api" # Placeholder
    }

@app.post("/api/scrape-videos", response_model=List[VideoData], tags=["Video Scraping (Generic URL)"])
async def post_scrape_videos_from_custom_url(request: ScrapeRequest):
    """Scrape video data from a user-provided URL (expects specific gallery-like HTML structure)."""
    videos = scrape_videos_from_url(str(request.url))
    if not videos:
        raise HTTPException(status_code=404, detail="No videos found on the provided webpage or structure not recognized.")
    return videos

@app.get("/api/stream/{video_page_link:path}", response_model=StreamData, tags=["Video Streams"])
async def get_stream_links_from_video_page(
    video_page_link: str = Path(..., description="Full URL of the hqporn.xxx video page.")
):
    """Scrapes a specific video page for direct stream links, poster, and sprites."""
    if not video_page_link.startswith(BASE_URL) and not video_page_link.startswith("http"): # Basic check
        raise HTTPException(status_code=400, detail=f"Invalid video_page_link. Must be a full URL, preferably from {BASE_URL}.")
    
    decoded_link = unquote(video_page_link) # Ensure path is decoded for scraper
    data = scrape_video_page_for_streams(decoded_link)
    if data.note and "Video player tag not found." in data.note and not data.main_video_src and not data.source_tags:
         raise HTTPException(status_code=404, detail="Video player content not found on the page.")
    return data

@app.get("/api/fresh/{page_number}", response_model=List[GenericVideoListItem], tags=["Video Listings (hqporn.xxx)"])
async def get_hqporn_fresh_page(page_number: int = Path(..., gt=0, description="Page number for fresh videos.")):
    scrape_url = f"{BASE_URL}/fresh/" if page_number == 1 else f"{BASE_URL}/fresh/{page_number}/"
    return scrape_hqporn_video_list_page(scrape_url)

@app.get("/api/search/{search_content}/{page_number}", response_model=List[GenericVideoListItem], tags=["Video Listings (hqporn.xxx)"])
async def get_hqporn_search_results_page(
    search_content: str = Path(..., description="Search query."),
    page_number: int = Path(..., gt=0, description="Page number for search results.")
):
    safe_search_content = quote(search_content)
    scrape_url = f"{BASE_URL}/search/{safe_search_content}/"
    if page_number > 1: scrape_url += f"{page_number}/"
    return scrape_hqporn_video_list_page(scrape_url)

@app.get("/api/pornstars/{page_number}", response_model=List[PornstarListItem], tags=["Pornstar Listings (hqporn.xxx)"])
async def get_hqporn_pornstars_page(page_number: int = Path(..., gt=0, description="Page number for pornstar listings.")):
    scrape_url = f"{BASE_URL}/pornstars/" if page_number == 1 else f"{BASE_URL}/pornstars/{page_number}/"
    return scrape_list_page_generic(
        scrape_url,
        container_sel=('div', {'id': 'galleries', 'class': 'js-pornstar-list'}),
        item_sel=('div', {'class': 'b-thumb-item--star'}),
        parser_func=_parse_pornstar_list_item, list_type="pornstars"
    )

@app.get("/api/best/{page_number}", response_model=List[GenericVideoListItem], tags=["Video Listings (hqporn.xxx)"])
async def get_hqporn_best_rated_page(page_number: int = Path(..., gt=0, description="Page for best-rated videos.")):
    scrape_url = f"{BASE_URL}/best/" if page_number == 1 else f"{BASE_URL}/best/{page_number}/"
    return scrape_hqporn_video_list_page(scrape_url)

@app.get("/api/trend/{page_number}", response_model=List[GenericVideoListItem], tags=["Video Listings (hqporn.xxx)"])
async def get_hqporn_trend_page(page_number: int = Path(..., gt=0, description="Page number for trending videos.")):
    # Specific URL structure for /trend/ as per original input_file_6.py
    scrape_url = f"{BASE_URL}/trend/{page_number}" 
    return scrape_hqporn_video_list_page(scrape_url)

@app.get("/api/categories/{page_number}", response_model=List[CategoryListItem], tags=["Category Listings (hqporn.xxx)"])
async def get_hqporn_categories_page(page_number: int = Path(..., gt=0, description="Page for category listings.")):
    # Specific URL structure for /categories/ as per original input_file_7.py
    scrape_url = f"{BASE_URL}/categories/" if page_number == 1 else f"{BASE_URL}/categories/{page_number}"
    return scrape_list_page_generic(
        scrape_url,
        container_sel=('div', {'id': 'galleries', 'class': 'js-category-list'}),
        item_sel=('div', {'class': 'b-thumb-item--cat'}),
        parser_func=_parse_category_list_item, list_type="categories"
    )

@app.get("/api/channels/{page_number}", response_model=List[ChannelListItem], tags=["Channel Listings (hqporn.xxx)"])
async def get_hqporn_channels_page(page_number: int = Path(..., gt=0, description="Page number for channel listings.")):
    scrape_url = f"{BASE_URL}/channels/" if page_number == 1 else f"{BASE_URL}/channels/{page_number}/"
    return scrape_list_page_generic(
        scrape_url,
        container_sel=('div', {'id': 'galleries', 'class': 'js-channel-list'}),
        item_sel=('div', {'class': 'b-thumb-item--cat'}), # Channels also use 'b-thumb-item--cat'
        parser_func=_parse_channel_list_item, list_type="channels"
    )

# --- Uvicorn runner for local development ---
if __name__ == "__main__":
    import uvicorn
    # For Render.com, they will use a command like: uvicorn main:app --host 0.0.0.0 --port $PORT
    # This block is for easy local running:
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
