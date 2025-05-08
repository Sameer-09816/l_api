import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import uvicorn

# Initialize FastAPI app
app = FastAPI(title="HQ Porn Scraper API")

# Configure CORS to allow requests from anywhere
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Base URL for scraping
BASE_URL = "https://hqporn.xxx"

# Pydantic Models
class Tag(BaseModel):
    link: str
    name: str

class ImageUrls(BaseModel):
    img_src: str
    jpeg: str
    webp: str

class VideoData(BaseModel):
    duration: str
    gallery_id: str
    image_urls: ImageUrls
    link: str
    preview_video_url: str
    tags: List[Tag]
    thumb_id: str
    title: str
    title_attribute: str

class CategoryData(BaseModel):
    link: str
    category_id: str
    title: str
    image_urls: ImageUrls

class PornstarData(BaseModel):
    link: str
    pornstar_id: str
    name: str
    image_urls: ImageUrls

class ChannelData(BaseModel):
    link: str
    channel_id: str
    name: str
    image_urls: ImageUrls

class SourceTag(BaseModel):
    src: str
    type: str
    size: str = None

class StreamData(BaseModel):
    video_page_url: str
    main_video_src: str = None
    source_tags: List[SourceTag]
    poster_image: str = None
    sprite_previews: List[str]

class ScrapeRequest(BaseModel):
    url: str

# Scraping Functions
def scrape_videos(url: str) -> List[VideoData]:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        video_items = soup.find_all("div", class_="b-thumb-item")

        videos = []
        for item in video_items:
            if "random-thumb" in item.get("class", []):
                continue

            title_elem = item.find("div", class_="b-thumb-item__title")
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

            link_elem = item.find("a", class_="js-gallery-link")
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
    except Exception as e:
        raise Exception(f"Error scraping videos: {str(e)}")

def scrape_categories(page_number: int) -> List[CategoryData]:
    if page_number <= 0:
        raise ValueError("Page number must be positive.")
    url = f"{BASE_URL}/categories/{page_number}/" if page_number > 1 else f"{BASE_URL}/categories/"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        category_list_container = soup.find('div', id='galleries', class_='js-category-list')
        if not category_list_container:
            return []

        items = category_list_container.find_all('div', class_='b-thumb-item--cat')
        categories = []
        for item in items:
            link_tag = item.find('a', class_='js-category-stats')
            if not link_tag:
                continue
            href = link_tag.get('href')
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            category_id = link_tag.get('data-category-id')
            title = link_tag.get('title', '').strip()

            picture_tag = item.find('picture')
            image_urls = ImageUrls(img_src="", jpeg="", webp="")
            if picture_tag:
                source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
                image_urls.webp = source_webp['srcset'] if source_webp and 'srcset' in source_webp.attrs else ""
                source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
                image_urls.jpeg = source_jpeg['srcset'] if source_jpeg and 'srcset' in source_jpeg.attrs else ""
                img_tag = picture_tag.find('img')
                if img_tag:
                    image_urls.img_src = img_tag.get('data-src', img_tag.get('src', ''))

            categories.append(CategoryData(
                link=link,
                category_id=category_id,
                title=title,
                image_urls=image_urls
            ))

        return categories
    except Exception as e:
        raise Exception(f"Error scraping categories: {str(e)}")

def scrape_pornstars(page_number: int) -> List[PornstarData]:
    if page_number <= 0:
        raise ValueError("Page number must be positive.")
    url = f"{BASE_URL}/pornstars/{page_number}/" if page_number > 1 else f"{BASE_URL}/pornstars/"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        pornstar_list_container = soup.find('div', id='galleries', class_='js-pornstar-list')
        if not pornstar_list_container:
            return []

        items = pornstar_list_container.find_all('div', class_='b-thumb-item--star')
        pornstars = []
        for item in items:
            link_tag = item.find('a', class_='js-pornstar-stats')
            if not link_tag:
                continue
            href = link_tag.get('href')
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            pornstar_id = link_tag.get('data-pornstar-id')
            name = link_tag.get('title', '').strip()

            picture_tag = item.find('picture')
            image_urls = ImageUrls(img_src="", jpeg="", webp="")
            if picture_tag:
                source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
                image_urls.webp = source_webp['srcset'] if source_webp and 'srcset' in source_webp.attrs else ""
                source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
                image_urls.jpeg = source_jpeg['srcset'] if source_jpeg and 'srcset' in source_jpeg.attrs else ""
                img_tag = picture_tag.find('img')
                if img_tag:
                    image_urls.img_src = img_tag.get('data-src', img_tag.get('src', ''))

            pornstars.append(PornstarData(
                link=link,
                pornstar_id=pornstar_id,
                name=name,
                image_urls=image_urls
            ))

        return pornstars
    except Exception as e:
        raise Exception(f"Error scraping pornstars: {str(e)}")

def scrape_channels(page_number: int) -> List[ChannelData]:
    if page_number <= 0:
        raise ValueError("Page number must be positive.")
    url = f"{BASE_URL}/channels/{page_number}/" if page_number > 1 else f"{BASE_URL}/channels/"
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        channel_list_container = soup.find('div', id='galleries', class_='js-channel-list')
        if not channel_list_container:
            return []

        items = channel_list_container.find_all('div', class_='b-thumb-item--cat')
        channels = []
        for item in items:
            link_tag = item.find('a', class_='js-channel-stats')
            if not link_tag:
                continue
            href = link_tag.get('href')
            link = f"{BASE_URL}{href}" if href and href.startswith('/') else href
            channel_id = link_tag.get('data-channel-id')
            name = link_tag.get('title', '').strip()

            picture_tag = item.find('picture')
            image_urls = ImageUrls(img_src="", jpeg="", webp="")
            if picture_tag:
                source_webp = picture_tag.find('source', attrs={'type': 'image/webp'})
                image_urls.webp = source_webp['srcset'] if source_webp and 'srcset' in source_webp.attrs else ""
                source_jpeg = picture_tag.find('source', attrs={'type': 'image/jpeg'})
                image_urls.jpeg = source_jpeg['srcset'] if source_jpeg and 'srcset' in source_jpeg.attrs else ""
                img_tag = picture_tag.find('img')
                if img_tag:
                    image_urls.img_src = img_tag.get('data-src', img_tag.get('src', ''))

            channels.append(ChannelData(
                link=link,
                channel_id=channel_id,
                name=name,
                image_urls=image_urls
            ))

        return channels
    except Exception as e:
        raise Exception(f"Error scraping channels: {str(e)}")

def scrape_stream_data(video_page_url: str) -> StreamData:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(video_page_url, headers=headers, timeout=20)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'html.parser')
        stream_data = StreamData(
            video_page_url=video_page_url,
            main_video_src=None,
            source_tags=[],
            poster_image=None,
            sprite_previews=[]
        )

        video_tag = soup.find('video', id='video_html5_api')
        if not video_tag:
            player_div = soup.find('div', class_='b-video-player')
            if player_div:
                video_tag = player_div.find('video')

        if video_tag:
            if video_tag.has_attr('src'):
                stream_data.main_video_src = video_tag['src']
            source_tags = video_tag.find_all('source')
            for source_tag in source_tags:
                if source_tag.has_attr('src'):
                    stream_data.source_tags.append(SourceTag(
                        src=source_tag['src'],
                        type=source_tag.get('type', ''),
                        size=source_tag.get('size', '')
                    ))
            if video_tag.has_attr('poster'):
                stream_data.poster_image = video_tag['poster']
            if video_tag.has_attr('data-preview'):
                sprite_string = video_tag['data-preview']
                stream_data.sprite_previews = [sprite.strip() for sprite in sprite_string.split(',') if sprite.strip()]

        return stream_data
    except Exception as e:
        raise Exception(f"Error scraping stream data: {str(e)}")

# API Endpoints
@app.get("/api/trend/{page_number}", response_model=List[VideoData])
async def get_trending_videos(page_number: int):
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    url = f"{BASE_URL}/trend/{page_number}/"
    try:
        return scrape_videos(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/best/{page_number}", response_model=List[VideoData])
async def get_best_videos(page_number: int):
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    url = f"{BASE_URL}/best/{page_number}/" if page_number > 1 else f"{BASE_URL}/best/"
    try:
        return scrape_videos(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fresh/{page_number}", response_model=List[VideoData])
async def get_fresh_videos(page_number: int):
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    url = f"{BASE_URL}/fresh/{page_number}/" if page_number > 1 else f"{BASE_URL}/fresh/"
    try:
        return scrape_videos(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search/{search_content}/{page_number}", response_model=List[VideoData])
async def get_search_results(search_content: str, page_number: int):
    if not search_content:
        raise HTTPException(status_code=400, detail="Search content cannot be empty.")
    if page_number <= 0:
        raise HTTPException(status_code=400, detail="Page number must be positive.")
    url = f"{BASE_URL}/search/{search_content}/{page_number}/" if page_number > 1 else f"{BASE_URL}/search/{search_content}/"
    try:
        return scrape_videos(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/categories/{page_number}", response_model=List[CategoryData])
async def get_categories(page_number: int):
    try:
        return scrape_categories(page_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/pornstars/{page_number}", response_model=List[PornstarData])
async def get_pornstars(page_number: int):
    try:
        return scrape_pornstars(page_number)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/channels/{page_number}", response_model=List[ChannelData])
async def get_channels(page_number: int):
    initially:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stream/{video_page_link:path}", response_model=StreamData)
async def get_stream_data(video_page_link: str):
    if not video_page_link.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid video page link. It must be a full URL.")
    try:
        return scrape_stream_data(video_page_link)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/scrape-videos", response_model=List[VideoData])
async def scrape_videos_endpoint(request: ScrapeRequest):
    try:
        videos = scrape_videos(request.url)
        if not videos:
            raise HTTPException(status_code=404, detail="No videos found on the provided webpage")
        return videos
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    return {
        "message": "Welcome to the HQ Porn Scraper API",
        "endpoints": {
            "/api/trend/{page_number}": "GET - Scrape trending videos",
            "/api/best/{page_number}": "GET - Scrape best-rated videos",
            "/api/fresh/{page_number}": "GET - Scrape fresh/newest videos",
            "/api/search/{search_content}/{page_number}": "GET - Scrape search results",
            "/api/categories/{page_number}": "GET - Scrape categories",
            "/api/pornstars/{page_number}": "GET - Scrape pornstars",
            "/api/channels/{page_number}": "GET - Scrape channels",
            "/api/stream/{video_page_link}": "GET - Scrape stream data from a video page",
            "/scrape-videos": "POST - Scrape videos from a provided URL",
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
