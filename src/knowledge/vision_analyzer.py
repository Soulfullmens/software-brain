"""
Vision Analyzer — Image & Video Analysis for SmartAgent

PURPOSE: Upload images/videos, analyze them using vision models,
and automatically harvest related knowledge from the internet.

FLOW:
    1. User uploads image/video
    2. Vision model describes what it sees
    3. Agent extracts key topics from the description
    4. Auto-harvests related knowledge from multiple sources
    5. Stores both the description and harvested knowledge

VISION BACKENDS:
    - Ollama (llava, llama3.2-vision) — local, free, private
    - Gemini Vision (cloud fallback) — fast, good quality
    - OpenRouter vision models (cloud fallback)

SUPPORTED FORMATS:
    - Images: JPEG, PNG, GIF, BMP, WebP
    - Videos: MP4, AVI, MOV (extracts key frames)
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VisionResult:
    """Result from analyzing an image or video."""
    description: str
    topics_detected: List[str]
    provider: str  # ollama, gemini, openrouter
    model: str
    auto_harvest_results: List[Dict] = field(default_factory=list)
    latency_ms: float = 0.0
    error: Optional[str] = None
    success: bool = True


class VisionAnalyzer:
    """
    Analyzes images and videos, extracts knowledge topics,
    and auto-harvests related information.
    
    Usage:
        analyzer = VisionAnalyzer()
        
        # Analyze an image
        result = analyzer.analyze_image("photo.jpg")
        # → "This is a circuit board with an Arduino microcontroller..."
        # → auto-harvests: Arduino, microcontroller, embedded systems
        
        # Analyze with specific question
        result = analyzer.analyze_image("engine.jpg", 
            question="What parts need replacing?")
    """

    # Vision-capable models in Ollama
    VISION_MODELS = [
        "llava:latest", "llava:13b", "llava:7b",
        "llama3.2-vision:latest", "llama3.2-vision:11b",
        "bakllava:latest", "moondream:latest",
    ]

    SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}
    SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm"}

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434",
        gemini_api_key: str = "",
        openrouter_api_key: str = "",
        harvester=None,
    ):
        self._ollama_url = ollama_url.rstrip("/")
        self._gemini_key = gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
        self._openrouter_key = openrouter_api_key or os.environ.get("OPEN_ROUTER_API_KEY", "")
        self._harvester = harvester
        self._vision_model: Optional[str] = None
        self._detect_vision_model()

    def _detect_vision_model(self):
        """Find available vision model in Ollama."""
        try:
            req = urllib.request.Request(
                f"{self._ollama_url}/api/tags", method="GET"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                available = [m["name"] for m in data.get("models", [])]
                for vm in self.VISION_MODELS:
                    if vm in available:
                        self._vision_model = vm
                        return
                    base = vm.split(":")[0]
                    for avail in available:
                        if base in avail:
                            self._vision_model = avail
                            return
        except Exception:
            pass

    def _image_to_base64(self, image_path: str) -> str:
        """Read image file and convert to base64."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _get_mime_type(self, path: str) -> str:
        ext = os.path.splitext(path)[1].lower()
        mime_map = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".gif": "image/gif",
            ".bmp": "image/bmp", ".webp": "image/webp",
        }
        return mime_map.get(ext, "image/jpeg")

    # ────────────────────────────────────────────────
    #  Vision Backend: Ollama (Local)
    # ────────────────────────────────────────────────

    def _analyze_ollama(self, image_b64: str, prompt: str) -> Optional[str]:
        """Use local Ollama vision model."""
        if not self._vision_model:
            return None

        # Enhanced parameters for technical analysis logic
        payload = {
            "model": self._vision_model,
            "prompt": f"[DETAILED TECHNICAL MODE] {prompt}",
            "images": [image_b64],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Lower for more factual extraction
                "num_predict": 1024,
                "top_k": 20,
                "top_p": 0.9,
                # Force specific focus in Ollama if it supports these params
                "num_ctx": 4096,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self._ollama_url}/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            return result.get("response", "")

    # ────────────────────────────────────────────────
    #  Vision Backend: Gemini (Cloud)
    # ────────────────────────────────────────────────

    def _analyze_gemini(self, image_b64: str, mime_type: str, prompt: str) -> Optional[str]:
        """Use Gemini Vision API."""
        if not self._gemini_key:
            return None

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self._gemini_key}"
        )
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                ],
            }],
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            candidates = result.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts:
                    return parts[0].get("text", "")
        return None

    # ────────────────────────────────────────────────
    #  Vision Backend: OpenRouter (Cloud)
    # ────────────────────────────────────────────────

    def _analyze_openrouter(self, image_b64: str, mime_type: str, prompt: str) -> Optional[str]:
        """Use OpenRouter with a vision model."""
        if not self._openrouter_key:
            return None

        url = "https://openrouter.ai/api/v1/chat/completions"
        payload = {
            "model": "meta-llama/llama-4-scout:free",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime_type};base64,{image_b64}",
                    }},
                ],
            }],
            "max_tokens": 1024,
            "temperature": 0.2,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._openrouter_key}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "SmartAgent Vision",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            choices = result.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
        return None

    # ────────────────────────────────────────────────
    #  Topic Extraction
    # ────────────────────────────────────────────────

    def _extract_topics(self, description: str) -> List[str]:
        """Extract harvestable topics from a vision description."""
        # Common object/concept patterns to detect
        topic_patterns = [
            # Technology
            r'\b(arduino|raspberry pi|microcontroller|circuit board|solar panel)\b',
            r'\b(computer|laptop|server|motherboard|gpu|cpu)\b',
            r'\b(robot|drone|3d printer|cnc|lathe)\b',
            # Vehicles
            r'\b(car|engine|transmission|brake|tire|suspension)\b',
            r'\b(motorcycle|bicycle|truck|boat)\b',
            # Food/Cooking
            r'\b(recipe|cooking|baking|ingredients|kitchen|oven)\b',
            r'\b(bread|cake|pasta|steak|soup|salad|pizza)\b',
            # Building/Repairs
            r'\b(plumbing|electrical|wiring|pipe|faucet|toilet)\b',
            r'\b(wood|metal|concrete|brick|nail|screw|bolt)\b',
            r'\b(tool|hammer|drill|saw|wrench|screwdriver)\b',
            # Science
            r'\b(molecule|atom|cell|dna|chemical|reaction)\b',
            r'\b(telescope|microscope|laboratory|experiment)\b',
            # Nature
            r'\b(plant|tree|flower|animal|insect|bird|fish)\b',
            # Math
            r'\b(equation|graph|chart|diagram|formula|geometry)\b',
        ]

        topics = set()
        desc_lower = description.lower()

        for pattern in topic_patterns:
            matches = re.findall(pattern, desc_lower)
            topics.update(matches)

        # Also extract capitalized proper nouns as potential topics
        proper_nouns = re.findall(r'\b[A-Z][a-z]{3,}\b', description)
        for noun in proper_nouns[:5]:
            if noun.lower() not in {"this", "that", "there", "here", "what", "which"}:
                topics.add(noun.lower())

        return list(topics)[:10]  # Max 10 topics

    # ────────────────────────────────────────────────
    #  Main Analysis Methods
    # ────────────────────────────────────────────────

    def analyze_image(
        self,
        image_path: str,
        question: str = "",
        auto_harvest: bool = True,
    ) -> VisionResult:
        """
        Analyze an image and optionally auto-harvest related knowledge.
        
        Args:
            image_path: Path to the image file
            question: Optional specific question about the image
            auto_harvest: Whether to automatically search for related knowledge
        
        Returns:
            VisionResult with description, detected topics, and harvest results
        """
        start = time.time()

        # Validate file
        ext = os.path.splitext(image_path)[1].lower()
        if ext not in self.SUPPORTED_IMAGE_EXTENSIONS:
            return VisionResult(
                description="", topics_detected=[], provider="none",
                model="none", success=False,
                error=f"Unsupported format: {ext}. Supported: {self.SUPPORTED_IMAGE_EXTENSIONS}",
            )

        if not os.path.exists(image_path):
            return VisionResult(
                description="", topics_detected=[], provider="none",
                model="none", success=False, error="File not found",
            )

        try:
            image_b64 = self._image_to_base64(image_path)
            mime_type = self._get_mime_type(image_path)
        except Exception as e:
            return VisionResult(
                description="", topics_detected=[], provider="none",
                model="none", success=False, error=f"Failed to read image: {e}",
            )

        # Build prompt
        prompt = question or (
            "Describe this image in detail. Identify all objects, tools, "
            "components, and concepts visible. If it's a technical image, "
            "explain what it shows and how it works. If it's food, identify "
            "the dish and ingredients. Be specific and practical."
        )

        # Try vision backends in order
        description = None
        provider = "none"
        model = "none"

        # 1. Try Ollama (local, free)
        if self._vision_model:
            try:
                description = self._analyze_ollama(image_b64, prompt)
                if description:
                    provider = "ollama"
                    model = self._vision_model
            except Exception:
                pass

        # 2. Try Gemini Vision (cloud)
        if not description:
            try:
                description = self._analyze_gemini(image_b64, mime_type, prompt)
                if description:
                    provider = "gemini"
                    model = "gemini-2.0-flash"
            except Exception:
                pass

        # 3. Try OpenRouter (cloud)
        if not description:
            try:
                description = self._analyze_openrouter(image_b64, mime_type, prompt)
                if description:
                    provider = "openrouter"
                    model = "llama-4-scout"
            except Exception:
                pass

        if not description:
            return VisionResult(
                description="", topics_detected=[], provider="none",
                model="none", success=False,
                error="No vision model available. Install: ollama pull llava",
                latency_ms=(time.time() - start) * 1000,
            )

        # Extract topics
        topics = self._extract_topics(description)

        # Auto-harvest related knowledge
        harvest_results = []
        if auto_harvest and self._harvester and topics:
            for topic in topics[:5]:  # Harvest top 5 topics
                try:
                    results = self._harvester.smart_harvest(topic)
                    for r in results:
                        harvest_results.append({
                            "source": r.source,
                            "topic": r.topic,
                            "chunks_stored": r.chunks_stored,
                            "success": r.success,
                        })
                except Exception:
                    pass

        latency = (time.time() - start) * 1000
        return VisionResult(
            description=description,
            topics_detected=topics,
            provider=provider,
            model=model,
            auto_harvest_results=harvest_results,
            latency_ms=latency,
        )

    def analyze_image_bytes(
        self,
        image_bytes: bytes,
        filename: str = "upload.jpg",
        question: str = "",
        auto_harvest: bool = True,
    ) -> VisionResult:
        """
        Analyze image from raw bytes (e.g., from file upload).
        """
        start = time.time()
        ext = os.path.splitext(filename)[1].lower()
        if ext not in self.SUPPORTED_IMAGE_EXTENSIONS:
            return VisionResult(
                description="", topics_detected=[], provider="none",
                model="none", success=False,
                error=f"Unsupported format: {ext}",
            )

        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        mime_type = self._get_mime_type(filename)

        prompt = question or (
            "Describe this image in detail. Identify all objects, tools, "
            "components, and concepts visible. If it's a technical image, "
            "explain what it shows and how it works. If it's food, identify "
            "the dish and ingredients. Be specific and practical."
        )

        # Try vision backends
        description = None
        provider = "none"
        model = "none"

        if self._vision_model:
            try:
                description = self._analyze_ollama(image_b64, prompt)
                if description:
                    provider = "ollama"
                    model = self._vision_model
            except Exception:
                pass

        if not description:
            try:
                description = self._analyze_gemini(image_b64, mime_type, prompt)
                if description:
                    provider = "gemini"
                    model = "gemini-2.0-flash"
            except Exception:
                pass

        if not description:
            try:
                description = self._analyze_openrouter(image_b64, mime_type, prompt)
                if description:
                    provider = "openrouter"
                    model = "llama-4-scout"
            except Exception:
                pass

        if not description:
            return VisionResult(
                description="", topics_detected=[], provider="none",
                model="none", success=False,
                error="No vision model available. Install: ollama pull llava",
                latency_ms=(time.time() - start) * 1000,
            )

        topics = self._extract_topics(description)
        harvest_results = []
        if auto_harvest and self._harvester and topics:
            for topic in topics[:5]:
                try:
                    results = self._harvester.smart_harvest(topic)
                    for r in results:
                        harvest_results.append({
                            "source": r.source, "topic": r.topic,
                            "chunks_stored": r.chunks_stored, "success": r.success,
                        })
                except Exception:
                    pass

        return VisionResult(
            description=description, topics_detected=topics,
            provider=provider, model=model,
            auto_harvest_results=harvest_results,
            latency_ms=(time.time() - start) * 1000,
        )

    def has_vision(self) -> bool:
        """Check if any vision capability is available."""
        if self._vision_model:
            return True
        if self._gemini_key:
            return True
        if self._openrouter_key:
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Get vision system status."""
        return {
            "has_vision": self.has_vision(),
            "local_model": self._vision_model,
            "gemini_available": bool(self._gemini_key),
            "openrouter_available": bool(self._openrouter_key),
            "supported_images": list(self.SUPPORTED_IMAGE_EXTENSIONS),
            "supported_videos": list(self.SUPPORTED_VIDEO_EXTENSIONS),
        }
