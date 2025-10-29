from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from typing import Any

from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

# Log Playwright environment on module import
logger.info(
    f"Playwright module loaded - browsers path: {os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 'not set')}"
)


async def capture_webpage(
    url: str,
    artifact_type: str = "pdf",
    viewport_width: int = 1920,
    viewport_height: int = 1080,
) -> dict[str, Any]:
    """
    Capture a webpage as PDF or PNG using Playwright.

    Args:
        url: Target URL to capture.
        artifact_type: 'png' or 'pdf'.
        viewport_width: Browser viewport width.
        viewport_height: Browser viewport height.

    Returns:
        dict: Capture result with binary data and metadata.
    """
    if artifact_type not in ("pdf", "png"):
        raise ValueError(f"Invalid artifact_type: {artifact_type}")

    logger.info(f"Starting Playwright capture for {url} as {artifact_type}")

    async with async_playwright() as p:
        # Log available browsers
        logger.info("Playwright context created, launching Chromium browser")

        # Use Chromium for consistency
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--single-process",
                "--disable-gpu",
                "--disable-web-security",
                "--disable-background-timer-throttling",
                "--disable-backgrounding-occluded-windows",
                "--disable-renderer-backgrounding",
                "--disable-features=TranslateUI",
                "--disable-ipc-flooding-protection",
                "--mute-audio",
                "--disable-extensions",
                "--disable-blink-features=AutomationControlled",
                "--use-angle=swiftshader",
                "--window-size=1920,1080",
                "--disable-features=VizDisplayCompositor",
                "--disable-background-media-suspend",
                "--disable-component-extensions-with-background-pages",
                "--disable-default-apps",
                "--disable-domain-reliability",
                "--disable-sync",
                "--enable-features=NetworkService,NetworkServiceLogging",
                "--force-color-profile=srgb",
            ],
        )

        context = await browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        )

        page = await context.new_page()

        try:
            # Navigate to URL with more robust loading strategy
            logger.info(f"Navigating to {url}")

            try:
                # First try networkidle with shorter timeout
                await page.goto(url, wait_until="networkidle", timeout=15000)
                logger.info(f"Page loaded successfully with networkidle for {url}")
            except Exception as e:
                logger.warning(f"NetworkIdle failed for {url}: {str(e)}, trying domcontentloaded")
                # Fallback to domcontentloaded if networkidle times out
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                logger.info(f"Page loaded with domcontentloaded for {url}")

            # Wait for dynamic content but with shorter timeout for problematic sites
            await page.wait_for_timeout(1500)

            # Generate the appropriate artifact based on type
            if artifact_type == "pdf":
                # Generate PDF with proper settings
                artifact_data = await page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "1cm", "right": "1cm", "bottom": "1cm", "left": "1cm"},
                    prefer_css_page_size=False,
                )
                logger.info(f"Generated PDF for {url}, size: {len(artifact_data)} bytes")
            else:
                # Generate PNG screenshot
                artifact_data = await page.screenshot(
                    full_page=False,  # Just the viewport to show "top of the page"
                    type="png",
                )
                logger.info(f"Generated PNG screenshot for {url}, size: {len(artifact_data)} bytes")

            # Calculate SHA-256 hash
            sha256_hash = hashlib.sha256(artifact_data).hexdigest()

            logger.info(f"Captured {url} as {artifact_type}, SHA-256: {sha256_hash}")

            return {
                "data": artifact_data,
                "sha256": sha256_hash,
                "artifact_type": artifact_type,
                "url": url,
                "content_length": len(artifact_data),
            }

        except Exception as e:
            logger.error(f"Error capturing {url}: {str(e)}")
            raise
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass


def capture_stub(url: str, artifact_type: str = "pdf") -> dict[str, Any]:
    """
    Synchronous wrapper for capture_webpage (for backwards compatibility).

    Args:
        url: Target URL.
        artifact_type: 'png' or 'pdf'.

    Returns:
        dict: Capture result.
    """
    return asyncio.run(capture_webpage(url, artifact_type))
