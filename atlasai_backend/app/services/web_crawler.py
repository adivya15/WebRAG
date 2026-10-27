"""
Web Crawler Service for WebRAG.

Features:
- Validates URLs (HTTP/HTTPS only).
- SSRF Protection: Blocks private IPs, loopbacks, link-local, and cloud metadata endpoints (169.254.169.254).
- Respects robots.txt via urllib.robotparser.
- Restricts crawling to approved website domain (netloc).
- Enforces configurable maximum pages and crawl depth.
- Polite rate-limiting and timeouts.
- Content extraction using BeautifulSoup:
  - Extracts title, meta description, headings (h1-h3), canonical URL, and main content.
  - Removes scripts, styles, navigation, footers, headers, forms, SVGs, and boilerplate.
- Handles broken links, timeouts, HTTP errors, and encoding issues.
- Avoids infinite loops and redundant crawls.
"""

import ipaddress
import logging
import re
import socket
import time
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, urlunparse
import urllib.robotparser

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_MAX_PAGES = 30
DEFAULT_MAX_DEPTH = 2
DEFAULT_TIMEOUT_SECONDS = 10
DEFAULT_POLITENESS_DELAY = 0.3  # Delay between requests in seconds
USER_AGENT = "WebRAG-Crawler/1.0 (+http://localhost/bot; academic research project)"

# Disallowed IP networks for SSRF protection
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),       # Private class A
    ipaddress.ip_network("172.16.0.0/12"),    # Private class B
    ipaddress.ip_network("192.168.0.0/16"),   # Private class C
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud metadata (AWS, GCP, Azure)
    ipaddress.ip_network("0.0.0.0/8"),        # Current network
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "instance-data",
}


class SSRFValidationError(ValueError):
    """Raised when a URL resolves to a forbidden internal or private network address."""
    pass


class CrawlLimitExceeded(Exception):
    """Raised when page limit is reached."""
    pass


def is_safe_url(url: str) -> bool:
    """
    Validates that a URL is safe to crawl:
    - Scheme must be http or https.
    - Hostname must resolve to a public, non-private, non-loopback IP address.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme.lower() not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    hostname = hostname.lower().strip()
    if hostname in BLOCKED_HOSTNAMES:
        return False

    # Check if hostname is an IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        for blocked_net in BLOCKED_IP_NETWORKS:
            if ip in blocked_net:
                return False
        return True
    except ValueError:
        pass  # It's a domain name, proceed to DNS resolution

    # Resolve domain to IP addresses to prevent DNS rebinding / SSRF
    try:
        addr_info = socket.getaddrinfo(hostname, None)
        for family, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            for blocked_net in BLOCKED_IP_NETWORKS:
                if ip in blocked_net:
                    return False
    except (socket.gaierror, socket.herror, Exception):
        # If DNS resolution fails, reject
        return False

    return True


def normalize_url(url: str) -> str:
    """Normalizes URL by stripping fragments and trailing slashes for deduplication."""
    parsed = urlparse(url)
    # Rebuild without fragment
    path = parsed.path
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        path if path else "/",
        parsed.params,
        parsed.query,
        ""  # Strip fragment
    ))
    return normalized


class WebCrawler:
    """Autonomous website crawler respecting domain constraints, robots.txt, and rate limits."""

    def __init__(
        self,
        start_url: str,
        max_pages: int = DEFAULT_MAX_PAGES,
        max_depth: int = DEFAULT_MAX_DEPTH,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        delay: float = DEFAULT_POLITENESS_DELAY,
        user_agent: str = USER_AGENT,
    ):
        if not is_safe_url(start_url):
            raise SSRFValidationError(f"Invalid or prohibited URL: {start_url}")

        self.start_url = normalize_url(start_url)
        parsed = urlparse(self.start_url)
        self.allowed_netloc = parsed.netloc.lower()
        self.base_scheme = parsed.scheme.lower()
        self.max_pages = max(1, min(max_pages, 100))
        self.max_depth = max(0, min(max_depth, 5))
        self.timeout = timeout
        self.delay = delay
        self.user_agent = user_agent

        self.visited_urls: Set[str] = set()
        self.crawled_pages: List[Dict] = []
        self.robot_parser: Optional[urllib.robotparser.RobotFileParser] = None

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

    def init_robots_txt(self) -> None:
        """Loads and parses robots.txt from the website root."""
        robots_url = f"{self.base_scheme}://{self.allowed_netloc}/robots.txt"
        self.robot_parser = urllib.robotparser.RobotFileParser()
        self.robot_parser.set_url(robots_url)
        try:
            if is_safe_url(robots_url):
                res = self.session.get(robots_url, timeout=self.timeout)
                if res.status_code == 200:
                    self.robot_parser.parse(res.text.splitlines())
                else:
                    self.robot_parser = None
        except Exception as e:
            logger.info("Could not fetch robots.txt for %s: %s", self.allowed_netloc, e)
            self.robot_parser = None

    def is_allowed_by_robots(self, url: str) -> bool:
        """Checks if URL is allowed under robots.txt."""
        if not self.robot_parser:
            return True
        try:
            return self.robot_parser.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def extract_page_data(self, html_content: str, current_url: str) -> Dict:
        """
        Parses HTML and extracts clean text, title, headings, meta tags, and outbound links.
        Strips non-content tags: nav, footer, header, scripts, styles, forms, ads.
        """
        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Extract Title
        title = "Untitled Page"
        if soup.title and soup.title.string:
            title = soup.title.string.strip()
        elif soup.find("h1"):
            title = soup.find("h1").get_text(strip=True)

        # 2. Extract Meta Description & Canonical URL
        meta_desc = ""
        meta_desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta_desc_tag and meta_desc_tag.get("content"):
            meta_desc = meta_desc_tag["content"].strip()

        canonical_url = current_url
        canonical_tag = soup.find("link", attrs={"rel": "canonical"})
        if canonical_tag and canonical_tag.get("href"):
            canonical_url = urljoin(current_url, canonical_tag["href"])

        # 3. Extract Headings
        headings: List[str] = []
        for h in soup.find_all(["h1", "h2", "h3"]):
            text = h.get_text(separator=" ", strip=True)
            if text and len(text) > 3 and text not in headings:
                headings.append(text)

        # 4. Extract Outbound Links before stripping navigation
        links: List[str] = []
        for a_tag in soup.find_all("a", href=True):
            raw_href = a_tag["href"].strip()
            if raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            full_url = urljoin(current_url, raw_href)
            normalized = normalize_url(full_url)
            parsed_link = urlparse(normalized)
            # Only add links within the same domain and safe schemes
            if parsed_link.netloc.lower() == self.allowed_netloc:
                if parsed_link.scheme.lower() in ("http", "https"):
                    # Avoid file downloads (images, pdfs, zips, etc.)
                    if not re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|tar|gz|exe|dmg|mp4|mp3)$", parsed_link.path, re.I):
                        links.append(normalized)

        # 5. Remove unwanted boilerplate tags
        for tag in soup.find_all([
            "script", "style", "nav", "footer", "header", "aside", "form",
            "noscript", "svg", "iframe", "button", "select"
        ]):
            tag.decompose()

        # Remove elements with common ad / banner / cookie classes
        for tag in soup.find_all(class_=re.compile(r"(cookie|banner|advertisement|sidebar|widget|popup)", re.I)):
            tag.decompose()

        # 6. Extract Main Content
        # Prefer <main> or <article> if available
        main_container = soup.find(["main", "article", "div[role='main']"])
        if main_container:
            text_body = main_container.get_text(separator="\n", strip=True)
        else:
            text_body = soup.get_text(separator="\n", strip=True)

        # Clean multiple blank lines
        lines = [line.strip() for line in text_body.splitlines() if line.strip()]
        clean_text = "\n".join(lines)

        return {
            "url": current_url,
            "canonical_url": canonical_url,
            "title": title,
            "meta_description": meta_desc,
            "headings": headings,
            "text": clean_text,
            "word_count": len(clean_text.split()),
            "outbound_links": list(set(links)),
        }

    def crawl(self, progress_callback=None) -> List[Dict]:
        """
        Executes breadth-first crawling up to max_pages and max_depth.
        Calls progress_callback(current_count, max_pages, current_url) if provided.
        """
        self.init_robots_txt()

        # Queue items: (url, current_depth)
        queue: List[tuple] = [(self.start_url, 0)]
        self.visited_urls.add(self.start_url)

        while queue and len(self.crawled_pages) < self.max_pages:
            url, depth = queue.pop(0)

            if not is_safe_url(url):
                continue

            if not self.is_allowed_by_robots(url):
                logger.info("Skipped by robots.txt: %s", url)
                continue

            try:
                if self.delay > 0:
                    time.sleep(self.delay)

                res = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                )

                # Ensure redirect didn't take us off-domain or to a private address
                final_url = normalize_url(res.url)
                if not is_safe_url(final_url) or urlparse(final_url).netloc.lower() != self.allowed_netloc:
                    continue

                content_type = res.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type and "application/xhtml" not in content_type:
                    continue

                if res.status_code != 200:
                    continue

                res.encoding = res.apparent_encoding or "utf-8"
                page_data = self.extract_page_data(res.text, final_url)
                page_data["depth"] = depth

                # Only keep pages with meaningful text
                if page_data["word_count"] >= 15:
                    self.crawled_pages.append(page_data)

                    if progress_callback:
                        progress_callback(
                            count=len(self.crawled_pages),
                            max_pages=self.max_pages,
                            url=final_url,
                            title=page_data["title"]
                        )

                # Enqueue child links if within max_depth
                if depth < self.max_depth:
                    for link in page_data["outbound_links"]:
                        if link not in self.visited_urls and len(self.visited_urls) < self.max_pages * 3:
                            self.visited_urls.add(link)
                            queue.append((link, depth + 1))

            except requests.exceptions.RequestException as e:
                logger.warning("Error fetching %s: %s", url, e)
                continue
            except Exception as e:
                logger.error("Unexpected error parsing %s: %s", url, e)
                continue

        return self.crawled_pages
