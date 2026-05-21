"""
web_archiver.py — Pre-Offline Data Caching

Solves the "accessing web data while offline" problem.
This module allows the agent to intelligently crawl, scrape, and summarize
live internet pages *while online*, and injects that knowledge directly
into the local Knowledge Graph. Once the agent goes offline (Airgap Mode),
that web data remains permanently searchable and accessible via local semantic search.
"""
import urllib.request
import urllib.parse
from html.parser import HTMLParser
import time
import logging
from typing import List, Optional

from .airgap_mode import require_internet
from ..intelligence.knowledge_graph import KnowledgeGraph

class SimpleHTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_lines = []
        self._ignore_tags = {'script', 'style', 'nav', 'footer', 'header'}
        self._in_ignored = False

    def handle_starttag(self, tag, attrs):
        if tag in self._ignore_tags:
            self._in_ignored = True

    def handle_endtag(self, tag):
        if tag in self._ignore_tags:
            self._in_ignored = False

    def handle_data(self, data):
        if not self._in_ignored:
            text = data.strip()
            if text:
                self.text_lines.append(text)

    def get_text(self) -> str:
        return " ".join(self.text_lines)


class WebArchiver:
    """Crawls URLs and stores their text locally in the Knowledge Graph for offline use."""
    def __init__(self, kg: KnowledgeGraph):
        self.kg = kg
        self.logger = logging.getLogger("WebArchiver")

    @require_internet
    def archive_url(self, url: str, topic_name: str) -> bool:
        """
        Download a webpage, parse the text, and save it to the local Knowledge Graph.
        Must be run while online.
        """
        self.logger.info(f"Archiving {url} under topic '{topic_name}'...")
        try:
            req = urllib.request.Request(
                url, 
                headers={'User-Agent': 'Mozilla/5.0 NomadAgent/1.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                content = response.read().decode('utf-8', errors='ignore')
                
            parser = SimpleHTMLTextExtractor()
            parser.feed(content)
            clean_text = parser.get_text()
            
            # Truncate if massive, we want the essence
            summary = clean_text[:2000] + ("..." if len(clean_text) > 2000 else "")
            
            # Inject into the offline brain
            # Create a "Topic" node
            self.kg.add_entity(topic_name, "web_archive", summary=f"Archived data from {url}")
            # Create a "Source" node
            source_domain = urllib.parse.urlparse(url).netloc
            self.kg.add_entity(source_domain, "domain", summary=f"Web source: {source_domain}")
            
            # Link them with the payload
            self.kg.add_relationship(
                source_name=topic_name,
                target_name=source_domain,
                relationship="archived_from",
                fact=summary,
                source="web_archiver"
            )
            
            self.logger.info(f"Successfully archived {len(clean_text)} characters for offline use.")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to archive {url}: {e}")
            return False

    @require_internet
    def batch_archive(self, archive_map: dict[str, str]) -> dict[str, bool]:
        """
        Take a dictionary of {url: topic} and archive all of them.
        """
        results = {}
        for url, topic in archive_map.items():
            success = self.archive_url(url, topic)
            results[url] = success
            time.sleep(1) # Be polite
        return results
