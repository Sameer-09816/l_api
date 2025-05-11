# main.py

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field # Use Field for parameter validation/metadata
from typing import List, Dict, Optional, Any
from urllib.parse import quote # Use quote for URL encoding search queries if constructing URL parts
import logging

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

class VideoData(BaseModel):
    """Model for video item data."""
    duration: Optional[str] = Field(None, description="Duration of the video (e.g., '12:34').")
    gallery_id: Optional[str] = Field(None, description="Unique ID for the video gallery/item on the site.")
    image_urls: ImageUrls
    link: Optional[str] = Field(None, description="Link to the full video page.")
    preview_video_url: Optional[str] = Field(None, description="URL for a short preview video.")
    tags: List[Tag] = Field([], description="List of tags/categories associated with the video.")
    thumb_id: Optional[str] = Field(None, description="Unique ID for the thumbnail/preview item.")
    title: Optional[str] = Field(None, description="Title of the video.")
    title_attribute: Optional[str] = Field(None, description="Value of the title attribute from the link tag.")

class ScrapeRequest(BaseModel):
    """Model for the request body when requesting a generic page scrape."""
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

def safe_scrape_page(url: str) -> Optional[BeautifulSoup]:
    """Fetches a URL and returns a BeautifulSoup object or None on error."""
    logger.info(f"Fetching: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        return BeautifulSoup(response.content, 'html.parser')
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {url}: {e}")
        # Raising HTTPException here simplifies error handling in endpoints
        raise HTTPException(status_code=500, detail=f"Failed to fetch or parse URL: {url} - {str(e)}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during scraping {url}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An internal error occurred while scraping {url}: {str(e)}")

def extract_image_urls(item_soup: BeautifulSoup) -> ImageUrls:
    """Extracts ImageUrls model from an item's BeautifulSoup element."""
    picture_tag = item_soup.find('picture', class_='js-gallery-img')
    # The pornstar/category items also have pictures, sometimes without js-gallery-img class
    if not picture_tag:
         picture_tag = item_soup.find('picture') # Fallback for other item types

    img_urls_data = {}
    if picture_tag:
        source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
        img_urls_data['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None

        source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
        img_urls_data['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None

        img_tag = picture_tag.find('img')
        if img_tag:
             # Prioritize data-src for lazy loading, fallback to src
            img_urls_data['img_src'] = img_tag.get('data-src', img_tag.get('src'))

    return ImageUrls(**img_urls_data)

def scrape_generic_video_list_page(section: str, page_number: int) -> List[VideoData]:
    """Scrapes lists of videos from pages like /fresh, /best, /trend."""
    # Adjust URL structure based on section and page number
    # /fresh/{page}/, /best/{page}/, /trend/{page}
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")

    if section == "trend":
         scrape_url = f"{BASE_URL}/trend/{page_number}" # No trailing slash seems common here
    elif page_number == 1:
         scrape_url = f"{BASE_URL}/{section}/" # Trailing slash for page 1 often
    else:
         scrape_url = f"{BASE_URL}/{section}/{page_number}/" # Trailing slash for other pages

    soup = safe_scrape_page(scrape_url) # This raises HTTPException on failure

    # Find the main container for gallery items
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')

    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}. No items found?")
        return [] # Indicate no items found, not necessarily an error

    items = gallery_list_container.find_all('div', class_='b-thumb-item')

    if not items:
        logger.info(f"No video items found on {scrape_url}.")
        return [] # Indicate no items found

    videos = []
    for item in items:
        # Skip random thumb items (e.g., ads) - added from input_file_0 logic
        if "random-thumb" in item.get("class", []):
            continue

        # Extract data following input_file_0/Flask app patterns
        title_elem = item.find("div", class_="b-thumb-item__title")
        title = title_elem.get_text(strip=True) if title_elem else None
        title_attribute = None # Initial assumption

        duration_elem = item.find("div", class_="b-thumb-item__duration")
        duration_span = duration_elem.find("span") if duration_elem else None
        duration = duration_span.get_text(strip=True) if duration_span else None

        image_urls_data = extract_image_urls(item) # Use the helper function

        link = None
        gallery_id = None
        thumb_id = None
        preview_video_url = None
        link_elem = item.find("a", class_="js-gallery-link")
        if link_elem:
            href = link_elem.get("href")
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            gallery_id = link_elem.get("data-gallery-id")
            thumb_id = link_elem.get("data-thumb-id")
            preview_video_url = link_elem.get("data-preview")
            title_attribute = link_elem.get("title") # Title attribute often has name

        # If title from title_elem was missing, use title_attribute as fallback
        if not title:
            title = title_attribute

        # Extract tags
        categories_elem = item.find("div", class_="b-thumb-item__detail")
        tags = []
        if categories_elem:
            # Check if it's just views/stats like "5M views", or actual tags
            # The Flask scraper looks for 'a' tags within detail.
            tag_links = categories_elem.find_all("a")
            tags = [
                Tag(
                    link=f"{BASE_URL}{link_a['href']}" if link_a.get('href', '').startswith('/') else link_a.get('href'),
                    name=link_a.get_text(strip=True)
                )
                for link_a in tag_links if link_a.get('href') and link_a.get_text(strip=True) # Ensure link and text are present
            ]

        # Ensure minimum data for a valid video item before appending
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
                 title_attribute=title_attribute # Store both if available
             )
             videos.append(video)
        else:
             logger.warning(f"Skipping video item due to missing link and title: {item.prettify()}")


    return videos

def scrape_search_page(search_content: str, page_number: int) -> List[VideoData]:
     """Scrapes search results pages."""
     if page_number <= 0:
         raise HTTPException(status_code=400, detail="Page number must be positive.")
     if not search_content:
         raise HTTPException(status_code=400, detail="Search content cannot be empty.")

     # Ensure search content is URL-encoded for the path
     safe_search_content = quote(search_content)

     # Search page URL structure: /search/term/ or /search/term/{page}/
     if page_number == 1:
         scrape_url = f"{BASE_URL}/search/{safe_search_content}/"
     else:
         scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/"


     soup = safe_scrape_page(scrape_url) # This raises HTTPException on failure

     # Check for explicit "No results found" message - adapted from input_file_1
     no_results_message = soup.find('div', class_='b-catalog-info-descr')
     if no_results_message and "no results found" in no_results_message.get_text(strip=True).lower():
          logger.info(f"Site reported 'No results found' for '{search_content}' on {scrape_url}")
          # Returning an empty list is generally better than 404 for search results,
          # as an empty result is a valid outcome.
          return []

     gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')

     if not gallery_list_container:
         logger.warning(f"Gallery list container not found on {scrape_url}. No items found?")
         return [] # Indicate no items found

     items = gallery_list_container.find_all('div', class_='b-thumb-item')

     if not items:
         logger.info(f"No video items found on {scrape_url} (after checking for no results message).")
         return [] # Indicate no items found


     # The item parsing logic is identical to generic video lists, reuse or replicate
     # Replicating for now, could refactor later
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
        link_elem = item.find("a", class_="js-gallery-link")
        if link_elem:
            href = link_elem.get("href")
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            gallery_id = link_elem.get("data-gallery-id")
            thumb_id = link_elem.get("data-thumb-id")
            preview_video_url = link_elem.get("data-preview")
            title_attribute = link_elem.get("title")

        if not title:
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
             logger.warning(f"Skipping search result item due to missing link and title: {item.prettify()}")

     return videos


def scrape_category_list_page(page_number: int) -> List[CategoryData]:
    """Scrapes the categories listing pages."""
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")

    scrape_url = f"{BASE_URL}/categories/{page_number}"
    if page_number == 1:
        scrape_url = f"{BASE_URL}/categories/" # Page 1 structure

    soup = safe_scrape_page(scrape_url) # This raises HTTPException on failure

    # Main container for categories
    category_list_container = soup.find('div', id='galleries', class_='js-category-list')

    if not category_list_container:
        logger.warning(f"Category list container not found on {scrape_url}. No items found?")
        return []

    # Category items have class 'b-thumb-item--cat'
    items = category_list_container.find_all('div', class_='b-thumb-item--cat')

    if not items:
        logger.info(f"No category items found on {scrape_url}.")
        return []

    scraped_data = []
    for item_soup in items:
        link_tag = item_soup.find('a', class_='js-category-stats')
        link = None
        category_id = None
        title = None # Primary title source
        if link_tag:
            href_relative = link_tag.get('href')
            link = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            category_id = link_tag.get('data-category-id')
            title = link_tag.get('title', '').strip() # Use <a> title primarily

        # Fallback/override title from the dedicated div
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True):
             # If <a> title was empty or less descriptive, use div title
            if not title or len(title) < len(title_div.get_text(strip=True)):
                 title = title_div.get_text(strip=True)


        image_urls = extract_image_urls(item_soup) # Use helper function

        if link and title: # Ensure essential data is present
            scraped_data.append(CategoryData(
                link=link,
                category_id=category_id,
                title=title,
                image_urls=image_urls
            ))
        else:
            logger.warning(f"Skipping category item due to missing title or link: {item_soup.prettify()}")


    return scraped_data


def scrape_pornstar_list_page(page_number: int) -> List[PornstarData]:
    """Scrapes the pornstar listing pages."""
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")

    scrape_url = f"{BASE_URL}/pornstars/{page_number}/" # Pages usually have trailing slash
    if page_number == 1:
        scrape_url = f"{BASE_URL}/pornstars/" # First page often has no page number

    soup = safe_scrape_page(scrape_url) # This raises HTTPException on failure

    # Main container for pornstars
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')

    if not pornstar_list_container:
        logger.warning(f"Pornstar list container not found on {scrape_url}. No items found?")
        # Could potentially be end of pagination or error page displaying something else
        # Check for typical gallery list instead to confirm potential end of pagination
        if soup.find('div', class_='js-gallery-list'):
             logger.info(f"Found a video/gallery list instead of pornstars on {scrape_url}. Likely end of pornstar pagination.")
        return []


    # Pornstar items class
    items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')

    if not items:
        logger.info(f"No pornstar items found on {scrape_url}.")
        return []

    scraped_data = []
    for item_soup in items:
        link_tag = item_soup.find('a', class_='js-pornstar-stats')
        link = None
        pornstar_id = None
        name = None # Primary name source
        if link_tag:
            href_relative = link_tag.get('href')
            link = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            pornstar_id = link_tag.get('data-pornstar-id')
            name = link_tag.get('title', '').strip() # Use <a> title primarily

        # Fallback for name from div if needed
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True):
             if not name: # Only use div title if <a> title was missing
                  name = title_div.get_text(strip=True)

        image_urls = extract_image_urls(item_soup) # Use helper function

        if link and name: # Ensure essential data is present
             scraped_data.append(PornstarData(
                 link=link,
                 pornstar_id=pornstar_id,
                 name=name,
                 image_urls=image_urls
             ))
        else:
             logger.warning(f"Skipping pornstar item due to missing name or link: {item_soup.prettify()}")

    return scraped_data

def scrape_channel_list_page(page_number: int) -> List[ChannelData]:
    """Scrapes the channel listing pages."""
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")

    scrape_url = f"{BASE_URL}/channels/{page_number}/" # Pages usually have trailing slash
    if page_number == 1:
        scrape_url = f"{BASE_URL}/channels/" # First page often has no page number

    soup = safe_scrape_page(scrape_url) # This raises HTTPException on failure

    # Main container for channels
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')

    if not channel_list_container:
        logger.warning(f"Channel list container not found on {scrape_url}. No items found?")
         # Check for typical gallery list instead
        if soup.find('div', class_='js-gallery-list'):
             logger.info(f"Found a video list instead of channels on {scrape_url}. Likely end of channel pagination.")
        return []


    # Channel items class
    items = channel_list_container.find_all('div', class_='b-thumb-item--cat') # Reuses cat class

    if not items:
        logger.info(f"No channel items found on {scrape_url}.")
        return []

    scraped_data = []
    for item_soup in items:
        link_tag = item_soup.find('a', class_='js-channel-stats')
        link = None
        channel_id = None
        name = None # Primary name source
        if link_tag:
            href_relative = link_tag.get('href')
            link = f"{BASE_URL}{href_relative}" if href_relative and href_relative.startswith('/') else href_relative
            channel_id = link_tag.get('data-channel-id')
            name = link_tag.get('title', '').strip() # Use <a> title primarily

        # Fallback or override name from the title div span
        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span') # Text is often inside a span
            if title_span and title_span.get_text(strip=True):
                 span_name = title_span.get_text(strip=True)
                 if not name or len(span_name) > len(name): # Prefer longer name if different
                     name = span_name


        image_urls = extract_image_urls(item_soup) # Use helper function

        if link and name: # Ensure essential data is present
             scraped_data.append(ChannelData(
                 link=link,
                 channel_id=channel_id,
                 name=name,
                 image_urls=image_urls
             ))
        else:
             logger.warning(f"Skipping channel item due to missing name or link: {item_soup.prettify()}")

    return scraped_data


def scrape_video_stream_data(video_page_url: str) -> StreamData:
    """Scrapes a single video page for stream links, poster, and sprites."""

    if not video_page_url or not video_page_url.startswith('http'):
         raise HTTPException(status_code=400, detail=f"Invalid video page URL provided: {video_page_url}")

    soup = safe_scrape_page(video_page_url) # This raises HTTPException on failure

    stream_data = StreamData(video_page_url=video_page_url) # Start with initial data

    # Locate the main video tag - ID is preferred as it's specific
    video_tag = soup.find('video', id='video_html5_api')
    # If ID not found, try a broader search for video within a player div
    if not video_tag:
        player_div = soup.find('div', class_='b-video-player')
        if player_div:
            video_tag = player_div.find('video')

    # If video tag is not found, it's likely a bad page or layout changed significantly
    if not video_tag:
        logger.warning(f"Video player tag not found on {video_page_url}. Cannot extract stream data.")
        raise HTTPException(status_code=404, detail="Video player tag not found on the page. Content may not be a video page or layout has changed.")
        # Alternative: Return stream_data with a note if a 404 isn't appropriate
        # stream_data.note = "Video player tag not found."
        # return stream_data

    # Extract primary src from video tag
    if video_tag.has_attr('src'):
        stream_data.main_video_src = video_tag['src']

    # Extract from <source> tags within the video tag
    found_sources = set() # Use set to avoid duplicates
    if stream_data.main_video_src:
         found_sources.add(stream_data.main_video_src) # Add primary src if it exists

    for source_tag in video_tag.find_all('source'):
        if source_tag.has_attr('src'):
            src_url = source_tag['src']
            # Only add source if not already seen and if src is not empty
            if src_url and src_url not in found_sources:
                 stream_data.source_tags.append(StreamSource(
                     src=src_url,
                     type=source_tag.get('type'),
                     size=source_tag.get('size') # 'size' attribute exists on some source tags for quality
                 ))
                 found_sources.add(src_url)

    # Check if any sources were found - if not, the video might be JS loaded or page is different
    if not stream_data.main_video_src and not stream_data.source_tags:
        logger.warning(f"No direct video src or source tags found on {video_page_url}.")
        stream_data.note = "No direct video <src> or <source> tags were found in the initial HTML parse. The video content might be loaded via JavaScript variables or a different method not covered by this basic scraper."


    # Extract poster image
    if video_tag.has_attr('poster'):
        stream_data.poster_image = video_tag['poster']

    # Extract sprite previews from data-preview attribute on video_tag
    if video_tag.has_attr('data-preview'):
        sprite_string = video_tag['data-preview']
        stream_data.sprite_previews = [sprite.strip() for sprite in sprite_string.split(',') if sprite.strip()]

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
            "/scrape-videos": "POST - Scrape video data from a generic listing URL.",
            "/api/fresh/{page_number}": "GET - Scrape fresh videos by page number.",
            "/api/best/{page_number}": "GET - Scrape best-rated videos by page number.",
            "/api/trend/{page_number}": "GET - Scrape trending videos by page number.",
            "/api/search/{search_content}/{page_number}": "GET - Search for videos by content and page number.",
            "/api/categories/{page_number}": "GET - Scrape categories list by page number.",
            "/api/pornstars/{page_number}": "GET - Scrape pornstars list by page number.",
            "/api/channels/{page_number}": "GET - Scrape channels list by page number.",
            "/api/stream/{video_page_link:path}": "GET - Scrape a specific video page for streaming links, poster, and sprites.",
        }
    }

@app.post("/scrape-videos", response_model=List[VideoData], summary="Scrape generic video listing page")
async def scrape_videos_endpoint(request: ScrapeRequest):
    """
    Scrape video data from the provided generic URL and return a list of video metadata.
    Suitable for URLs found from links to video lists within the site.
    """
    videos = scrape_generic_video_list_page(request.url.replace(f"{BASE_URL}/", "").strip('/'), 1) # Attempt to guess section and page=1, simplified. Or call directly based on structure?
    # Reverting to original input_file_0 logic which scrapes ANY URL structure
    # and specifically finds .b-thumb-item. It was more general purpose.
    # The scrape_generic_video_list_page is specific to /section/page structure.
    # Let's restore the general purpose scraper function for this endpoint.

    logger.info(f"Attempting to scrape videos from generic URL: {request.url}")
    try:
        response = requests.get(request.url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
         raise HTTPException(status_code=500, detail=f"Error fetching URL {request.url}: {str(e)}")

    soup = BeautifulSoup(response.text, "html.parser")
    # Find any thumb items that might be video items (excludes channel/star/cat specific classes)
    video_items = soup.find_all("div", class_="b-thumb-item js-thumb-item js-thumb") # Based on input_file_0

    videos = []
    for item in video_items:
        if "random-thumb" in item.get("class", []):
            continue # Skip ads or random suggestions

        # --- Extract data - replicating logic from original scrape_videos ---
        title_elem = item.find("div", class_="b-thumb-item__title js-gallery-title")
        title = title_elem.get_text(strip=True) if title_elem else None
        title_attribute = title # Initial assumption, will be overridden by link tag title if available

        duration_elem = item.find("div", class_="b-thumb-item__duration")
        duration_span = duration_elem.find("span") if duration_elem else None
        duration = duration_span.get_text(strip=True) if duration_span else None

        image_urls_data = extract_image_urls(item) # Use helper

        link = None
        gallery_id = None
        thumb_id = None
        preview_video_url = None
        link_elem = item.find("a", class_="js-gallery-stats js-gallery-link")
        if link_elem:
            href = link_elem.get("href")
            # Original added hqporn.xxx if relative link. Be cautious if URL isn't from base.
            # Assume internal relative link needs BASE_URL prepended.
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            gallery_id = link_elem.get("data-gallery-id")
            thumb_id = link_elem.get("data-thumb-id")
            preview_video_url = link_elem.get("data-preview")
            link_title_attribute = link_elem.get("title")
            if link_title_attribute:
                title_attribute = link_title_attribute # Use the title from the link tag if available

        # Final decision on video title
        if not title: # If title was missing from the specific title div
             title = title_attribute # Use link tag title

        # Extract tags
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

        # Ensure minimum data before creating model
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
                title_attribute=title_attribute # Include attribute for completeness
            )
            videos.append(video)
        else:
            logger.warning(f"Skipping item scraped from {request.url} due to missing link/title: {item.prettify()}")

    if not videos:
        # Check if it's a gallery list page but empty, or potentially a non-list page
        if not soup.find('div', id='galleries') and not soup.find_all("div", class_="b-thumb-item"):
            raise HTTPException(status_code=404, detail="The provided URL does not appear to be a recognizable video listing page.")
        else:
             # It is a listing page but found no items
             logger.info(f"Scraped {request.url} but found 0 video items.")
             # Returning 200 with an empty list is more standard for an empty list
             return []

    return videos


@app.get("/api/fresh/{page_number}", response_model=List[VideoData], summary="Get Fresh Videos Page")
async def get_fresh_page(
    page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Retrieve videos from the '/fresh' section by page number."""
    return scrape_generic_video_list_page(section="fresh", page_number=page_number)

@app.get("/api/best/{page_number}", response_model=List[VideoData], summary="Get Best Rated Videos Page")
async def get_best_rated_page(
     page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Retrieve videos from the '/best' section by page number."""
    return scrape_generic_video_list_page(section="best", page_number=page_number)


@app.get("/api/trend/{page_number}", response_model=List[VideoData], summary="Get Trending Videos Page")
async def get_trend_page(
     page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Retrieve videos from the '/trend' section by page number."""
    # Note: This uses a potentially different URL structure based on observation from input_file_8
    return scrape_generic_video_list_page(section="trend", page_number=page_number)

@app.get("/api/search/{search_content}/{page_number}", response_model=List[VideoData], summary="Search Videos")
async def get_search_results_page(
    search_content: str = Path(..., description="The search query."),
    page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Search for videos using a query and retrieve results by page number."""
    if not search_content:
        raise HTTPException(status_code=400, detail="Search content cannot be empty.")
    return scrape_search_page(search_content=search_content, page_number=page_number)


@app.get("/api/categories/{page_number}", response_model=List[CategoryData], summary="Get Categories Page")
async def get_categories_page(
     page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Retrieve categories from the '/categories' section by page number."""
    return scrape_category_list_page(page_number=page_number)


@app.get("/api/pornstars/{page_number}", response_model=List[PornstarData], summary="Get Pornstars Page")
async def get_pornstars_page(
     page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Retrieve pornstars from the '/pornstars' section by page number."""
    return scrape_pornstar_list_page(page_number=page_number)


@app.get("/api/channels/{page_number}", response_model=List[ChannelData], summary="Get Channels Page")
async def get_channels_page(
     page_number: int = Path(..., description="The page number (must be > 0)", gt=0)
):
    """Retrieve channels from the '/channels' section by page number."""
    return scrape_channel_list_page(page_number=page_number)

@app.get("/api/stream/{video_page_link:path}", response_model=StreamData, summary="Get Stream Links for a Video Page")
async def get_stream_links(
    # Using ':path' allows this variable to contain '/' characters
    video_page_link: str = Path(..., description="The full URL of the video page to scrape for stream links (e.g., https://hqporn.xxx/video-title_123.html). Must start with http.")
):
    """Scrape a specific video playback page for its direct streaming links."""
    return scrape_video_stream_data(video_page_url=video_page_link)


# --- Main execution block for running with uvicorn ---

if __name__ == "__main__":
    import uvicorn
    # Use environment variable $PORT for Render deployment compatibility
    import os
    port = int(os.environ.get("PORT", 8000)) # Default to 8000 if PORT env var not set
    uvicorn.run(app, host="0.0.0.0", port=port)
