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
            title = "Webpage Capture"

            # Extract title from HTML if possible
            if "<title>" in content and "</title>" in content:
                start = content.find("<title>") + 7
                end = content.find("</title>", start)
                if end > start:
                    title = content[start:end].strip()

        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            content = f"Failed to fetch webpage: {e}"
            title = "Capture Failed"

    # Create a visual representation of the webpage
    # Generate a screenshot-like image that represents the webpage
    img_width, img_height = 1200, 1600
    img = Image.new("RGB", (img_width, img_height), color="white")
    draw = ImageDraw.Draw(img)

    try:
        # Try to use a default font, fallback to basic if not available
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
    except:
        font_title = None
        font_text = None

    # Draw header with URL and title
    y_pos = 20
    draw.rectangle([0, 0, img_width, 80], fill="#f8f9fa", outline="#dee2e6")
    draw.text((20, 20), f"Captured: {url}", fill="#495057", font=font_title)
    draw.text((20, 45), title[:80], fill="#212529", font=font_title)

    y_pos = 100

    # Extract and display key content from HTML
    # Remove script and style tags
    clean_html = re.sub(r"<script[^>]*>.*?</script>", "", content, flags=re.DOTALL | re.IGNORECASE)
    clean_html = re.sub(r"<style[^>]*>.*?</style>", "", clean_html, flags=re.DOTALL | re.IGNORECASE)

    # Extract text content
    text_content = re.sub(r"<[^>]+>", " ", clean_html)
    text_content = re.sub(r"\s+", " ", text_content).strip()

    # Draw content blocks to simulate webpage layout
    content_blocks = text_content[:1500].split(".")  # First 1500 chars, split by sentences

    for block in content_blocks[:20]:  # Limit to 20 blocks
        if not block.strip():
            continue

        block = block.strip()[:120]  # Limit block length
        if len(block) < 10:  # Skip very short blocks
            continue

        # Draw a content block
        block_height = 40
        if y_pos + block_height > img_height - 50:
            break

        # Draw block background
        draw.rectangle(
            [20, y_pos, img_width - 20, y_pos + block_height], fill="#ffffff", outline="#e9ecef"
        )

        # Draw text content
        draw.text((30, y_pos + 10), block, fill="#212529", font=font_text)

        y_pos += block_height + 10

    # Convert PIL image to PDF
    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # Convert PIL image to format that ReportLab can use
    img_buffer = BytesIO()
    img.save(img_buffer, format="PNG")
    img_buffer.seek(0)

    # Scale image to fit PDF page
    img_reader = ImageReader(img_buffer)

    # Calculate scaling to fit page width while maintaining aspect ratio
    pdf_width = width - 40  # Leave margins
    scale = pdf_width / img_width
    scaled_height = img_height * scale

    # If image is too tall, scale to fit height instead
    if scaled_height > height - 40:
        scale = (height - 40) / img_height
        scaled_height = height - 40
        pdf_width = img_width * scale

    # Center the image on the page
    x_offset = (width - pdf_width) / 2
    y_offset = height - 20 - scaled_height

    # Draw the image
    p.drawImage(img_reader, x_offset, y_offset, pdf_width, scaled_height)

    # Add footer with capture info
    p.setFont("Helvetica", 8)
    p.setFillColor("#666666")
    p.drawString(20, 20, "Captured via Simple HTTP Engine | SHA-256 will be calculated")

    p.save()
    artifact_data = buffer.getvalue()

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
