"""Simple capture engine using requests and HTML-to-PDF conversion."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

logger = logging.getLogger(__name__)

MIN_BLOCK_LENGTH = 10


async def capture_webpage_simple(
    url: str,
    artifact_type: str = "pdf",
    viewport_width: int = 1920,
    viewport_height: int = 1080,
) -> dict[str, Any]:
    """
    Simple capture function using HTTP requests and PDF generation.

    Args:
        url: Target URL to capture.
        artifact_type: 'pdf' or 'png' (only PDF supported for now).
        viewport_width: Ignored for simple capture.
        viewport_height: Ignored for simple capture.

    Returns:
        dict: Capture result with PDF data and metadata.
    """
    if artifact_type not in ("pdf", "png"):
        raise ValueError(f"Invalid artifact_type: {artifact_type}")

    if artifact_type == "png":
        raise NotImplementedError("PNG capture not implemented in simple engine")

    # Fetch webpage content
    content, title = await fetch_webpage_content(url)

    # Extract and display key content from HTML
    blocks = extract_text_blocks(content)

    # Create a visual representation of the webpage
    # Generate a screenshot-like image that represents the webpage
    img = render_webpage_image(url, title, blocks)

    # Convert PIL image to PDF
    artifact_data = image_to_pdf(img)

    # Calculate SHA-256 hash
    sha256_hash = hashlib.sha256(artifact_data).hexdigest()

    logger.info(f"Simple captured {url} as {artifact_type}, SHA-256: {sha256_hash}")

    return {
        "data": artifact_data,
        "sha256": sha256_hash,
        "artifact_type": artifact_type,
        "url": url,
        "content_length": len(artifact_data),
        "capture_method": "simple_http",
    }


async def fetch_webpage_content(url: str) -> tuple[str, str]:
    """Fetch HTML content and title from a webpage."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                follow_redirects=True,
            )
            response.raise_for_status()
            content = response.text
            title = extract_title(content)
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            content = f"Failed to fetch webpage: {e}"
            title = "Capture Failed"
    return content, title


def extract_title(html: str) -> str:
    """Extract the title tag from HTML content."""
    if "<title>" in html and "</title>" in html:
        start = html.find("<title>") + 7
        end = html.find("</title>", start)
        if end > start:
            return html[start:end].strip()
    return "Webpage Capture"


def extract_text_blocks(
    html: str, max_chars: int = 1500, max_blocks: int = 20, min_block_length: int = 10
) -> list[str]:
    """Clean HTML and split into text blocks for drawing."""
    clean_html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style[^>]*>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)
    text_content = re.sub(r"<[^>]+>", " ", clean_html)
    text_content = re.sub(r"\s+", " ", text_content).strip()
    blocks = []
    for raw_block in text_content[:max_chars].split(".")[:max_blocks]:
        block = raw_block.strip()[:120]
        if len(block) >= min_block_length:
            blocks.append(block)
    return blocks


def render_webpage_image(
    url: str, title: str, content_blocks: list[str], img_width: int = 1200, img_height: int = 1600
) -> Image.Image:
    """Draw the webpage representation as an image."""
    img = Image.new("RGB", (img_width, img_height), color="white")
    draw = ImageDraw.Draw(img)

    try:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
    except Exception:
        font_title = None
        font_text = None

    # Header
    y_pos = 20
    draw.rectangle([0, 0, img_width, 80], fill="#f8f9fa", outline="#dee2e6")
    draw.text((20, 20), f"Captured: {url}", fill="#495057", font=font_title)
    draw.text((20, 45), title[:80], fill="#212529", font=font_title)
    y_pos = 100

    # Draw content blocks
    for block in content_blocks:
        block_height = 40
        if y_pos + block_height > img_height - 50:
            break
        draw.rectangle(
            [20, y_pos, img_width - 20, y_pos + block_height], fill="#ffffff", outline="#e9ecef"
        )
        draw.text((30, y_pos + 10), block, fill="#212529", font=font_text)
        y_pos += block_height + 10

    return img


def image_to_pdf(img: Image.Image) -> bytes:
    """Convert a PIL image to a PDF byte array."""
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    img_reader = ImageReader(img_buffer)

    pdf_width = width - 40
    scale = pdf_width / img.width
    scaled_height = img.height * scale

    if scaled_height > height - 40:
        scale = (height - 40) / img.height
        scaled_height = height - 40
        pdf_width = img.width * scale

    x_offset = (width - pdf_width) / 2
    y_offset = height - 20 - scaled_height

    p.drawImage(img_reader, x_offset, y_offset, pdf_width, scaled_height)
    p.setFont("Helvetica", 8)
    p.setFillColor("#666666")
    p.drawString(20, 20, "Captured via Simple HTTP Engine | SHA-256 will be calculated")
    p.save()
    return buffer.getvalue()


def capture_simple_stub(url: str, artifact_type: str = "pdf") -> dict[str, Any]:
    """
    Synchronous wrapper for capture_webpage_simple.

    Args:
        url: Target URL.
        artifact_type: 'pdf' only.

    Returns:
        dict: Capture result.
    """
    return asyncio.run(capture_webpage_simple(url, artifact_type))
