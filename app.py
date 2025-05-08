import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import logging
import os
from urllib.parse import quote
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="HQ Porn Scraper API", description="API for scraping video, category, pornstar, and channel data from hqporn.xxx")

# Add CORS middleware to allow requests from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://hqporn.xxx"

# Pydantic models
class ScrapeRequest(BaseModel):
    url: str

class Tag(BaseModel):
    link: str
    name: str

class ImageUrls(BaseModel):
    img_src: str
    jpeg: Optional[str]
    webp: Optional[str]

class VideoData(BaseModel):
    duration: Optional[str]
    gallery_id: Optional[str]
    image_urls: ImageUrls
    link: str
    preview_video_url: Optional[str]
    tags: List[Tag]
    thumb_id: Optional[str]
    title: str
    title_attribute: Optional[str]

class StreamSource(BaseModel):
    src: str
    type: Optional[str]
    size: Optional[str]

class StreamData(BaseModel):
    video_page_url: str
    main_video_src: Optional[str]
    source_tags: List[StreamSource]
    poster_image: Optional[str]
    sprite_previews: List[str]
    note: Optional[str]

class CategoryData(BaseModel):
    link: str
    category_id: Optional[str]
    title: str
    image_urls: ImageUrls

class PornstarData(BaseModel):
    link: str
    pornstar_id: Optional[str]
    name: str
    image_urls: ImageUrls

class ChannelData(BaseModel):
    link: str
    channel_id: Optional[str]
    name: str
    image_urls: ImageUrls

# Scraping functions
def scrape_video_page_for_streams(video_page_url: str) -> Dict:
    logger.info(f"Attempting to scrape stream links from: {video_page_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(video_page_url, headers=headers, timeout=20)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {video_page_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching video page: {str(e)}")

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
    found_sources = set([stream_data["main_video_src"]]) if stream_data["main_video_src"] else set()
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

def scrape_videos(url: str) -> List[VideoData]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
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
            link = link_elem["href"] if link_elem and "href" in link_elem.attrs else ""
            if link and not link.startswith("http"):
                link = f"{BASE_URL}{link}"
            gallery_id = link_elem["data-gallery-id"] if link_elem and "data-gallery-id" in link_elem.attrs else "Unknown"

            preview_video_url = link_elem["data-preview"] if link_elem and "data-preview" in link_elem.attrs else ""
            thumb_id = link_elem["data-thumb-id"] if link_elem and "data-thumb-id" in link_elem.attrs else "Unknown"

            categories_elem = item.find("div", class_="b-thumb-item__detail")
            tags = []
            if categories_elem:
                category_links = categories_elem.find_all("a")
                tags = [
                    Tag(
                        link=link["href"] if link["href"].startswith("http") else f"{BASE_URL}{link['href']}",
                        name=link.get_text(strip=True)
                    )
                    for link in category_links
                ]

            video = VideoData(
                duration=duration,
                gallery_id=gallery_id,
                image_urls=ImageUrls(img_src=img_src, jpeg=jpeg, webp=webp),
                link=link,
                preview_video_url=preview_video_url,
                tags=tags,
                thumb_id=thumb_id,
                title=title,
                title_attribute=title_attribute
            )
            videos.append(video)
        return videos
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Error fetching webpage: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing webpage: {str(e)}")

def scrape_generic_page(section: str, page_number: int) -> List[VideoData]:
    scrape_url = f"{BASE_URL}/{section}/{page_number}/" if page_number > 1 else f"{BASE_URL}/{section}/"
    logger.info(f"Attempting to scrape {section} page: {scrape_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching {section} page: {str(e)}")

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        logger.warning(f"Gallery list container not found on {scrape_url}.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on page {page_number} of /{section}/.")
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
        data['title'] = title_div.get_text(strip=True) if title_div else data.get('title_attribute', 'N/A')

        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) if img_tag else None
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

        scraped_data.append(VideoData(**data))
    return scraped_data

def scrape_search_page(search_content: str, page_number: int) -> List[VideoData]:
    safe_search_content = quote(search_content)
    scrape_url = f"{BASE_URL}/search/{safe_search_content}/{page_number}/" if page_number > 1 else f"{BASE_URL}/search/{safe_search_content}/"
    logger.info(f"Attempting to scrape search results for '{search_content}' (page {page_number}): {scrape_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching search page: {str(e)}")

    soup = BeautifulSoup(response.content, 'html.parser')
    gallery_list_container = soup.find('div', id='galleries', class_='js-gallery-list')
    if not gallery_list_container:
        no_results_message = soup.find('div', class_='b-catalog-info-descr')
        if no_results_message and "no results found" in no_results_message.get_text(strip=True).lower():
            logger.info(f"No search results found for '{search_content}' on {scrape_url}.")
        return []

    items = gallery_list_container.find_all('div', class_='b-thumb-item')
    if not items:
        logger.info(f"No items found on page {page_number} for search '{search_content}'.")
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
        data['title'] = title_div.get_text(strip=True) if title_div else data.get('title_attribute', 'N/A')

        picture_tag = item_soup.find('picture', class_='js-gallery-img')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) if img_tag else None
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

        scraped_data.append(VideoData(**data))
    return scraped_data

def scrape_categories_page(page_number: int) -> List[CategoryData]:
    scrape_url = f"{BASE_URL}/categories/{page_number}/" if page_number > 1 else f"{BASE_URL}/categories/"
    logger.info(f"Attempting to scrape categories from: {scrape_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching categories page: {str(e)}")

    soup = BeautifulSoup(response.content, 'html.parser')
    category_list_container = soup.find('div', id='galleries', class_='js-category-list')
    if not category_list_container:
        if soup.find('div', class_='js-gallery-list'):
            logger.warning(f"Found a video list instead of categories on {scrape_url}.")
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
        else:
            logger.warning("Found a category item with no js-category-stats link.")
            continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div and title_div.get_text(strip=True):
            if not data.get('title'):
                data['title'] = title_div.get_text(strip=True)

        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) if img_tag else None
        data['image_urls'] = image_urls

        if data.get('title') and data.get('link'):
            scraped_data.append(CategoryData(**data))
    return scraped_data

def scrape_pornstars_page(page_number: int) -> List[PornstarData]:
    scrape_url = f"{BASE_URL}/pornstars/{page_number}/" if page_number > 1 else f"{BASE_URL}/pornstars/"
    logger.info(f"Attempting to scrape pornstars from: {scrape_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching pornstars page: {str(e)}")

    soup = BeautifulSoup(response.content, 'html.parser')
    pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
    if not pornstar_list_container:
        if soup.find('div', class_='js-gallery-list'):
            logger.warning(f"Found a video list instead of pornstars on {scrape_url}.")
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
            image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) if img_tag else None
        data['image_urls'] = image_urls

        if data.get('name') and data.get('link'):
            scraped_data.append(PornstarData(**data))
    return scraped_data

def scrape_channels_page(page_number: int) -> List[ChannelData]:
    scrape_url = f"{BASE_URL}/channels/{page_number}/" if page_number > 1 else f"{BASE_URL}/channels/"
    logger.info(f"Attempting to scrape channels from: {scrape_url}")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(scrape_url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching {scrape_url}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching channels page: {str(e)}")

    soup = BeautifulSoup(response.content, 'html.parser')
    channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')
    if not channel_list_container:
        if soup.find('div', class_='js-gallery-list'):
            logger.warning(f"Found a video list instead of channels on {scrape_url}.")
        return []

    items = channel_list_container.find_all('div', class_='b-thumb-item--cat')
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
        else:
            logger.warning("Found a channel item with no js-channel-stats link.")
            continue

        title_div = item_soup.find('div', class_='b-thumb-item__title')
        if title_div:
            title_span = title_div.find('span')
            if title_span and title_span.get_text(strip=True) and not data.get('name'):
                data['name'] = title_span.get_text(strip=True)

        picture_tag = item_soup.find('picture')
        image_urls = {}
        if picture_tag:
            source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
            image_urls['webp'] = source_webp['srcset'] if source_webp and source_webp.has_attr('srcset') else None
            source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
            image_urls['jpeg'] = source_jpeg['srcset'] if source_jpeg and source_jpeg.has_attr('srcset') else None
            img_tag = picture_tag.find('img')
            image_urls['img_src'] = img_tag.get('data-src', img_tag.get('src')) if img_tag else None
        data['image_urls'] = image_urls

        if data.get('name') and data.get('link'):
            scraped_data.append(ChannelData(**data))
    return scraped_data

# API endpoints
@app.post("/api/scrape-videos", responsemania = List[VideoData])
async def scrape_videos_endpoint(request: ScrapeRequest):
    """
    Scrape video data from the provided URL and return a list of video metadata.
    """
    videos = scrape_videos(request.url)
    if not videos:
        raise HTTPException(status_code=404, detail="No videos found on the provided webpage")
    return videos

@app.get("/api/stream/{video_page_link:path}", response_model=StreamData)
async def get_stream_links(video_page_link: str):
    """
    Scrape streaming links, poster, and sprite previews from a video page URL.
    """
    if not video_page_link.startswith("http"):
        raise HTTPException(status_code=400, detail=f"Invalid video_page_link. It must be a full URL. Received: {video_page_link}")
    data = scrape_video_page_for_streams(video_page_link)
    if "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])
    return data

@app.get("/api/fresh/{page_number}", response_model=List[VideoData])
async def get_fresh_page(page_number: int):
    """
    Scrape fresh (newest) videos from hqporn.xxx/fresh/ for the specified page.
    """
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_generic_page("fresh", page_number)

@app.get("/api/search/{search_content}/{page_number}", response_model=List[VideoData])
async def get_search_results_page(search_content: str, page_number: int):
    """
    Scrape search results for the given query and page number.
    """
    if not search_content:
        raise HTTPException(status_code=400, detail="Search content cannot be empty.")
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_search_page(search_content, page_number)

@app.get("/api/best/{page_number}", response_model=List[VideoData])
async def get_best_rated_page(page_number: int):
    """
    Scrape best (top-rated) videos from hqporn.xxx/best/ for the specified page.
    """
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_generic_page("best", page_number)

@app.get("/api/categories/{page_number}", response_model=List[CategoryData])
async def get_categories_page(page_number: int):
    """
    Scrape categories from hqporn.xxx/categories/ for the specified page.
    """
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_categories_page(page_number)

@app.get("/api/trend/{page_number}", response_model=List[VideoData])
async def get_trend_page(page_number: int):
    """
    Scrape trending videos from hqporn.xxx/trend/ for the specified page.
    """
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_generic_page("trend", page_number)

@app.get("/api/pornstars/{page_number}", response_model=List[PornstarData])
async def get_pornstars_page(page_number: int):
    """
    Scrape pornstars from hqporn.xxx/pornstars/ for the specified page.
    """
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_pornstars_page(page_number)

@app.get("/api/channels/{page_number}", response_model=List[ChannelData])
async def get_channels_page(page_number: int):
    """
    Scrape channels from hqporn.xxx/channels/ for the specified page.
    """
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    return scrape_channels_page(page_number)

@app.get("/")
async def root():
    """
    Root endpoint providing basic API information.
    """
    return {
        "message": "Welcome to the HQ Porn Scraper API",
        "endpoints": {
            "/api/scrape-videos": "POST - Scrape video data from a provided URL",
            "/api/stream/{video_page_link}": "GET - Scrape streaming links from a video page",
            "/api/fresh/{page_number}": "GET - Scrape fresh videos",
            "/api/search/{search_content}/{page_number}": "GET - Scrape search results",
            "/api/best/{page_number}": "GET - Scrape best-rated videos",
            "/api/categories/{page_number}": "GET - Scrape categories",
            "/api/trend/{page_number}": "GET - Scrape trending videos",
            "/api/pornstars/{page_number}": "GET - Scrape pornstars",
            "/api/channels/{page_number}": "GET - Scrape channels"
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))  # Use PORT env var for Render.com
    uvicorn.run(app, host="0.0.0.0", port=port)
