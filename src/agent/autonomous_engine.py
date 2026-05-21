"""
Autonomous Engine — LLM-Powered Think → Plan → Act → Observe Loop

NO hardcoded patterns. The LLM understands natural language and decides:
1. THINK: What does the user want?
2. PLAN: What steps are needed?
3. ACT: Execute each step using tools
4. OBSERVE: Check the result, adapt if needed
5. RESPOND: Tell the user what happened

This makes the agent work like a human — you say what you want,
it figures out HOW to do it.
"""

from __future__ import annotations

import json
import os
import re
import time
import threading
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.tools.desktop_control import DesktopControl, ActionResult
from src.tools.browser_automation import BrowserAutomation, BrowserResult

try:
    from src.agent.llm_router import (
        LLMRouter, LLMRequest, LLMResponse, ToolDefinition, ToolCall,
        Message, Role,
    )
    LLM_ROUTER_AVAILABLE = True
except ImportError:
    LLM_ROUTER_AVAILABLE = False

try:
    from src.agent.security.security_kernel import (
        SecurityKernel, SecurityResult as SecResult,
        ActionVerdict, ThreatLevel, AuthorityLevel,
    )
    SECURITY_AVAILABLE = True
except ImportError:
    SECURITY_AVAILABLE = False

try:
    from src.knowledge.vision_analyzer import VisionAnalyzer
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

# Domains the agent considers safe by default
SAFE_DOMAINS = {
    "google.com", "youtube.com", "wikipedia.org", "github.com",
    "stackoverflow.com", "reddit.com", "twitter.com", "x.com",
    "linkedin.com", "instagram.com", "facebook.com", "amazon.com",
    "microsoft.com", "apple.com", "bbc.com", "cnn.com",
    "netflix.com", "spotify.com", "duckduckgo.com", "bing.com",
    # Entertainment / streaming
    "hianime.to", "aniwatch.to", "crunchyroll.com", "funimation.com",
    "9anime.to", "myanimelist.net", "imdb.com", "rottentomatoes.com",
    "twitch.tv", "disneyplus.com", "hulu.com", "primevideo.com",
    "hotstar.com", "jiocinema.com", "zee5.com", "sonyliv.com",
    "vimeo.com", "dailymotion.com", "archive.org",
    # Shopping / utilities
    "flipkart.com", "myntra.com", "ebay.com", "walmart.com",
    "maps.google.com", "weather.com", "translate.google.com",
    # Education
    "coursera.org", "udemy.com", "khanacademy.org", "edx.org",
    "w3schools.com", "geeksforgeeks.org", "medium.com",
}

# Map engine tool names → SecurityKernel sandbox tool names
_TOOL_NAME_MAP = {
    "browser": "browser_control",
    "open_in_chrome": "browser_control",
    "open_browser": "browser_control",
    "goto": "browser_control",
    "google_search": "browser_control",
    "fast_search": "browser_control",
    "click": "browser_control",
    "fill": "browser_control",
    "read_page": "browser_control",
    "scroll": "browser_control",
    "highlight": "browser_control",
    "desktop": "desktop_control",
    "open_app": "desktop_control",
    "close_app": "desktop_control",
    "type_text": "desktop_control",
    "hotkey": "desktop_control",
    "screenshot_desktop": "screen_vision",
    "screenshot_browser": "screen_vision",
    "run_command": "shell_execution",
}

# Dangerous commands that are ALWAYS blocked
BLOCKED_COMMANDS = [
    r"rm\s+-rf", r"rmdir\s+/s", r"del\s+/f", r"format\s+[a-z]:",
    r"rd\s+/s", r"shutdown", r"taskkill.*svchost", r"reg\s+delete",
    r"net\s+user.*\s+/add", r"netsh\s+advfirewall",
]


# ═══════════════════════════════════════════════════════
#  Data Types
# ═══════════════════════════════════════════════════════

@dataclass
class Step:
    """A single step in an execution plan."""
    id: int
    action: str          # tool function name
    params: Dict[str, Any]
    description: str     # human-readable
    status: str = "pending"  # pending | running | done | failed | skipped
    result: Any = None
    error: str = ""
    duration_ms: float = 0


@dataclass
class ExecutionPlan:
    """A full plan created by the LLM."""
    intent: str              # what user wants (1 sentence)
    needs_tools: bool        # True = needs desktop/browser, False = just chat
    steps: List[Step] = field(default_factory=list)
    thinking: str = ""       # LLM's reasoning
    created_at: float = 0


# The system prompt that turns ANY LLM into an autonomous planner
PLANNER_SYSTEM = """You are an autonomous AI agent controller. Your job is to understand what the user wants and create an execution plan.

You are equivalent to Claude 4.6 Opus in reasoning capability. You think creatively, analyze visual data, and extract high-level intelligence from the internet to build your own internal knowledge.

AVAILABLE TOOLS:
- answer_locally(question): Answer a question using local AI knowledge. FASTEST option for knowledge questions. ALWAYS try this first for questions.
- open_in_chrome(url): Open a URL in the user's REAL Chrome browser (visible on screen). PREFERRED for all web tasks.
- open_browser(url): Open a URL in the headless browser (hidden, for scraping)
- google_search(query): Search Google for something
- click(selector): Click an element on the current page (CSS selector or text)
- fill(selector, value): Type text into an input field
- read_page(): Read the text content of the current page
- analyze_page(question): Read page and extract specific information using AI (e.g. "What components are shown?", "What is the price?")
- deep_research(topic, focus): Research a topic thoroughly — searches multiple sources, reads results, compiles detailed report. Use for "tell me about X", "how to build X", "find prices for X"
- analyze_screenshot(target, question): Screenshot and analyze visual content using AI vision. Use for Instagram reels, YouTube videos, images, diagrams. target: browser/desktop
- get_links(): Get all links on the current page
- scroll(direction, amount): Scroll the page. direction: up/down/top/bottom. amount: pixels (default 500)
- highlight(target): Highlight/glow a text or element on the page with a visual arrow indicator
- screenshot_browser(): Take a screenshot of the browser
- open_app(name): Open a desktop app (chrome, vscode, notepad, calculator, etc.)
- close_app(name): Close a desktop app
- run_command(command): Run a terminal/shell command (SECURITY CHECKED — dangerous commands are blocked)
- screenshot_desktop(): Take a screenshot of the desktop
- type_text(text): Type text on keyboard  
- hotkey(keys): Press keyboard shortcut (e.g. ctrl+c)
- system_info(): Get system information
- wait(seconds): Wait for something to load
- DONE: No more steps needed

RESPONSE FORMAT — You MUST respond with ONLY valid JSON, no other text:
{
  "intent": "brief description of what user wants",
  "needs_tools": true,
  "thinking": "your reasoning about how to accomplish this. Think like Claude 4.6 Opus — be creative, thorough, and analytical.",
  "steps": [
    {"action": "tool_name", "params": {"key": "value"}, "description": "what this step does"},
    {"action": "tool_name", "params": {"key": "value"}, "description": "what this step does"}
  ]
}

If the user is just chatting/asking a question (no tools needed):
{
  "intent": "user wants to know about X",
  "needs_tools": false,
  "thinking": "this is a knowledge question, no tools needed",
  "steps": []
}

RULES:
1. Be smart — understand INTENT, not just keywords. "I want to watch Dhurander" means search for movie + find streaming site + play it
2. CRITICAL: DON'T JUST OPEN TABS — you must READ pages, EXTRACT info, and REPORT BACK to the user with detailed findings
3. For research tasks (how to build, where to buy, what components), use deep_research() — it does multi-source research automatically
4. VISION MANDATE: Be EXTREMELY suspicious of single-frame vision. For videos (YouTube, Instagram, TikTok), you MUST MANDATE a multi-frame strategy: 
   - Take at least 3-4 screenshots at different timestamps (scroll or wait between them).
   - Use analyze_screenshot() for each one.
   - Cross-reference visual markers (wires, circuit boards, carbon fiber, propellers, nozzles, motors) across frames before concluding.
   - NEVER assume "woodworking" if you see wires; NEVER assume "DIY box" if you see an ESC or flight controller.
5. After visiting any page, use analyze_page(question) to extract the specific info the user needs
6. Always search Google first when you need to find something online
7. After searching, ALWAYS read_page() to see the results before clicking blindly
8. Use wait(2) between page navigations to let pages load
9. Be thorough — research tasks need detailed answers with prices, links, steps
10. Keep action steps focused but complete (3-15 steps depending on complexity)
11. Params must match the tool signatures exactly
12. For google_search, use a good search query — be specific
13. For click, use descriptive text that would match a link/button on the page
14. Think step by step — what would a human do?
15. After clicking a link, add read_page() to verify you landed on the right page
16. DISTILLATION: Your successful plans and insights are stored to train local smaller models. Act as an expert 'Teacher' model.
17. SECURITY: Never run shell commands that delete files, format drives, or modify system settings
18. SECURITY: Never enter user credentials or payment information without explicit user confirmation
19. SECURITY: Protect user's data — never send files or data to external servers
20. Use scroll() to navigate long pages and find specific content
21. Use highlight() after finding the answer to visually show it to the user
22. For knowledge questions, use answer_locally() first — it's instant and works offline

EXAMPLE — "Search for latest AI news on Google":
{
  "intent": "search Google for latest AI news and read results",
  "needs_tools": true,
  "thinking": "I'll search Google, wait for results, then read the page to extract the news headlines",
  "steps": [
    {"action": "google_search", "params": {"query": "latest AI news 2025"}, "description": "Search Google for latest AI news"},
    {"action": "wait", "params": {"seconds": 2}, "description": "Wait for results to load"},
    {"action": "read_page", "params": {}, "description": "Read the search results page to find headlines"},
    {"action": "screenshot_browser", "params": {}, "description": "Take screenshot to verify results"}
  ]
}

EXAMPLE — "Open YouTube and play a song":
{
  "intent": "open YouTube and play a song",
  "needs_tools": true,
  "thinking": "I'll go to YouTube, search for the song, read results, then click play",
  "steps": [
    {"action": "open_browser", "params": {"url": "https://www.youtube.com"}, "description": "Open YouTube"},
    {"action": "wait", "params": {"seconds": 2}, "description": "Wait for YouTube to load"},
    {"action": "fill", "params": {"selector": "input[name=search_query]", "value": "song name"}, "description": "Type song in search box"},
    {"action": "click", "params": {"selector": "button#search-icon-legacy"}, "description": "Click search button"},
    {"action": "wait", "params": {"seconds": 2}, "description": "Wait for results"},
    {"action": "read_page", "params": {}, "description": "Read results to find the right video"},
    {"action": "click", "params": {"selector": "ytd-video-renderer a"}, "description": "Click the first video result"}
  ]
}

EXAMPLE — "Check this Instagram reel and tell me what tools they use to build that robot":
{
  "intent": "analyze Instagram reel about robotics, identify components/tools used, research them",
  "needs_tools": true,
  "thinking": "I'll open the Instagram link, take a screenshot to see the visual content, analyze what components and tools are shown, then research each one to find prices and where to buy",
  "steps": [
    {"action": "open_in_chrome", "params": {"url": "https://www.instagram.com/reel/..."}, "description": "Open the Instagram reel in Chrome"},
    {"action": "wait", "params": {"seconds": 3}, "description": "Wait for reel to load"},
    {"action": "analyze_screenshot", "params": {"target": "desktop", "question": "What robot components, tools, motors, microcontrollers, and building materials are visible? What are they building and how?"}, "description": "Analyze what's shown in the reel"},
    {"action": "deep_research", "params": {"topic": "mini robot building components and tools", "focus": "components needed, prices, where to buy, beginner guide"}, "description": "Research the components and tools identified"},
    {"action": "DONE", "params": {}, "description": "Report all findings to user"}
  ]
}

EXAMPLE — "Research how to build a mini robot on small budget":
{
  "intent": "research mini robot building - components, tools, costs, tutorials",
  "needs_tools": true,
  "thinking": "I'll do deep research on mini robot building covering components, budget, and step-by-step guide",
  "steps": [
    {"action": "deep_research", "params": {"topic": "how to build a mini robot on small budget", "focus": "components list with prices, tools needed, step-by-step tutorial, beginner friendly"}, "description": "Research mini robot building comprehensively"},
    {"action": "DONE", "params": {}, "description": "Report detailed findings"}
  ]
}"""


# Lighter prompt for quick intent detection (is this a tool task or just chat?)
QUICK_DETECT_PROMPT = """Classify this user message. Reply with ONLY one word: TOOL or CHAT

TOOL = user wants you to DO something (open app, browse web, search, control computer, watch/play/download something, fill form, etc.)
CHAT = user is asking a question, having a conversation, or wants information from your knowledge

Examples:
"I want to watch a bollywood movie" → TOOL
"What is machine learning?" → CHAT
"Open chrome and go to github" → TOOL  
"Remember I like dark mode" → CHAT
"Find me a good restaurant nearby" → TOOL
"How are you?" → CHAT
"Play some music" → TOOL
"What's the capital of France?" → CHAT
"Search for Python tutorials" → TOOL
"Explain quantum computing" → CHAT

User message: """


# ═══════════════════════════════════════════════════════
#  Claude Native Tool Definitions
# ═══════════════════════════════════════════════════════

def _build_jarvis_tools() -> list:
    """Build ToolDefinition list for Claude native tool calling."""
    if not LLM_ROUTER_AVAILABLE:
        return []
    return [
        ToolDefinition(
            name="open_in_chrome",
            description="Open a URL in the user's real Chrome browser (visible on screen). Use for all web browsing.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The full URL to open (must start with http:// or https://)"},
                },
                "required": ["url"],
            },
        ),
        ToolDefinition(
            name="google_search",
            description="Search Google. Opens results in the headless browser for scraping.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        ),
        ToolDefinition(
            name="fast_search",
            description="Fast Google search that returns structured results (title, snippet, URL) without opening a browser. Preferred for information retrieval.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query"},
                },
                "required": ["query"],
            },
        ),
        ToolDefinition(
            name="goto",
            description="Navigate the headless browser to a URL (for scraping, not visible to user).",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL to navigate to"},
                },
                "required": ["url"],
            },
        ),
        ToolDefinition(
            name="click",
            description="Click an element on the current page. Can use CSS selector or visible text.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector or visible text of the element to click"},
                },
                "required": ["selector"],
            },
        ),
        ToolDefinition(
            name="fill",
            description="Type text into an input field on the current page.",
            parameters={
                "type": "object",
                "properties": {
                    "selector": {"type": "string", "description": "CSS selector of the input field"},
                    "value": {"type": "string", "description": "Text to type into the field"},
                },
                "required": ["selector", "value"],
            },
        ),
        ToolDefinition(
            name="read_page",
            description="Read the text content of the current page in the headless browser.",
            parameters={
                "type": "object",
                "properties": {},
            },
        ),
        ToolDefinition(
            name="scroll",
            description="Scroll the current page.",
            parameters={
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "enum": ["up", "down", "top", "bottom"], "description": "Scroll direction"},
                    "amount": {"type": "integer", "description": "Pixels to scroll (default 500)", "default": 500},
                },
                "required": ["direction"],
            },
        ),
        ToolDefinition(
            name="highlight",
            description="Highlight/glow a text or element on the page with a visual arrow indicator.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Text or CSS selector to highlight"},
                },
                "required": ["target"],
            },
        ),
        ToolDefinition(
            name="open_app",
            description="Open a desktop application (chrome, vscode, notepad, calculator, terminal, etc.).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Application name"},
                },
                "required": ["name"],
            },
        ),
        ToolDefinition(
            name="type_text",
            description="Type text using the keyboard (simulates real keystrokes).",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                },
                "required": ["text"],
            },
        ),
        ToolDefinition(
            name="hotkey",
            description="Press a keyboard shortcut (e.g. 'ctrl+c', 'alt+tab').",
            parameters={
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Key combination separated by + (e.g. 'ctrl+c')"},
                },
                "required": ["keys"],
            },
        ),
        ToolDefinition(
            name="run_command",
            description="Run a terminal/shell command. Dangerous commands are blocked by security.",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The shell command to execute"},
                },
                "required": ["command"],
            },
        ),
        ToolDefinition(
            name="screenshot",
            description="Take a screenshot of the desktop or browser.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["desktop", "browser"], "description": "What to screenshot", "default": "desktop"},
                },
            },
        ),
        ToolDefinition(
            name="answer_locally",
            description="Answer a question using local AI knowledge. FASTEST option — use this first for knowledge questions before searching the web.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The question to answer"},
                },
                "required": ["question"],
            },
        ),
        ToolDefinition(
            name="wait",
            description="Wait for a specified number of seconds (e.g. for a page to load).",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Seconds to wait (max 10)", "default": 2},
                },
            },
        ),
        ToolDefinition(
            name="done",
            description="Signal that the task is complete. Call this when you've finished all steps and want to report back to the user.",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief summary of what was accomplished"},
                },
                "required": ["summary"],
            },
        ),
        ToolDefinition(
            name="analyze_page",
            description="Read the current page and use AI to extract specific information. Use this after navigating to a page when you need to find specific details (prices, components, instructions, names, etc). Much better than raw read_page for research tasks.",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "What specific information to extract from the page (e.g. 'What components and tools are shown?', 'What are the prices?', 'What steps are described?')"},
                },
                "required": ["question"],
            },
        ),
        ToolDefinition(
            name="deep_research",
            description="Research a topic thoroughly: searches multiple sources, reads top results, and compiles a detailed summary. Use this when the user wants detailed information, comparisons, prices, how-to guides, or analysis of a topic. Returns a compiled research report.",
            parameters={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "The topic to research in detail"},
                    "focus": {"type": "string", "description": "Specific focus area (e.g. 'prices and where to buy', 'how to build', 'components needed', 'step by step guide')", "default": "general"},
                },
                "required": ["topic"],
            },
        ),
        ToolDefinition(
            name="analyze_screenshot",
            description="Take a screenshot of the browser or desktop and analyze what's visible using AI vision. Use this for visual content like Instagram reels, videos, images, or any page where you need to SEE what's displayed (not just read text). Returns a detailed description of what's visible.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "enum": ["desktop", "browser"], "description": "What to screenshot and analyze", "default": "browser"},
                    "question": {"type": "string", "description": "What to look for in the screenshot (e.g. 'What tools and components are visible?', 'What is being built?')", "default": "Describe everything you see in detail."},
                },
            },
        ),
    ]


JARVIS_TOOLS = _build_jarvis_tools()

TOOL_USE_SYSTEM = """You are Jarvis — an autonomous AI agent that controls a computer to help the user.

You have access to tools for browsing the web, controlling desktop apps, running commands, and answering questions.

## REASONING
Before EVERY tool call, think through:
1. What is the user's end goal?
2. What information do I already have? What am I missing?
3. What's the most efficient next step?
4. Could this step fail? What's my fallback?

Always explain your reasoning in your response text BEFORE calling tools.

## CRITICAL: RESEARCH & ANALYZE — DON'T JUST OPEN TABS
- Your job is to FIND ANSWERS and REPORT BACK, not just open browser tabs.
- When the user asks about a topic, you MUST read pages, extract info, and compile a detailed response.
- Use deep_research for thorough multi-source research on any topic.
- Use analyze_page after visiting a page to extract specific details (prices, components, steps, etc).
- VISION MANDATE: Be EXTREMELY suspicious of single-frame vision. For videos (YouTube, Instagram, TikTok), you MUST MANDATE a multi-frame strategy: 
   - Take at least 3-4 screenshots at different timestamps (scroll or wait between them).
   - Use analyze_screenshot() for each one.
   - Cross-reference visual markers (wires, circuit boards, carbon fiber, propellers, nozzles, motors) across frames before concluding.
   - NEVER assume "woodworking" if you see wires; NEVER assume "DIY box" if you see an ESC or flight controller.
- Use analyze_screenshot to see visual content (Instagram reels, videos, images, diagrams).
- ALWAYS compile your findings into a detailed done(summary) at the end — the user needs to READ your answer.
- For link analysis (Instagram, YouTube, etc): open the link → analyze_screenshot to see what's shown → research the topics found → report everything.

## RULES
- Understand the user's INTENT, not just their words. "I want to watch Dhurander" means find and play that movie.
- For knowledge questions, use answer_locally first — it's instant. Only search the web if you're unsure.
- For web browsing tasks, prefer open_in_chrome (visible to user) over goto (headless/hidden).
- After navigation, use read_page or analyze_page to observe what's on the page before taking more actions.
- Use wait(2) between page navigations to let pages load.
- Keep actions focused but thorough — research tasks may need 8-15 tool calls.
- Call the done tool with a DETAILED summary when you've completed the task — include all findings, prices, links, steps.
- NEVER run dangerous shell commands (rm -rf, format, shutdown, etc.).
- NEVER enter credentials or payment info without explicit user confirmation.
- If you've done a similar task before (see PAST EXPERIENCE below), reuse what worked.
- If a step fails, try an alternative approach — don't repeat the same failing action.
- Think step by step. After each tool result, decide if you need more info or can proceed.

## SMART BEHAVIORS
- If a search returns no results, try rephrasing the query or a different search engine.
- If a page takes too long to load, try a different URL or skip to the next step.
- If you're unsure about something, read_page first to gather context before acting.
- Verify your work: after completing a task, briefly confirm the result is correct.
- Be proactive: if the user mentions a topic, research related aspects they might need (prices, alternatives, tutorials).
- For Instagram/YouTube/video links: ALWAYS analyze_screenshot to see what's actually shown, then research the things you see.
- When reporting back, be DETAILED: include component names, prices, where to buy, step-by-step instructions.
- If the user wants to build something, research: components needed, tools required, estimated cost, difficulty level, tutorial links.
"""


# ═══════════════════════════════════════════════════════
#  Autonomous Engine
# ═══════════════════════════════════════════════════════

class AutonomousEngine:
    """
    The brain that turns natural language into autonomous action.
    
    Works like a real AI agent — observe, think, act, adapt:
    
    1. UNDERSTAND: Parse what the user wants
    2. PLAN: Create step-by-step execution plan
    3. ACT: Execute each step with tools
    4. OBSERVE: Check the result after each step
    5. ADAPT: If something failed, replan and retry
    6. VERIFY: After all steps, check if the goal was achieved
    7. CONTINUE: If not done, create a follow-up plan (up to MAX_ROUNDS)
    
    This is the difference between a script and an agent:
    A script executes steps blindly; an agent observes results and adapts.
    """

    MAX_ROUNDS = 3          # max plan→execute→observe cycles per request
    MAX_RETRIES_PER_STEP = 2  # retry failed steps with replanning
    MAX_TOOL_ROUNDS = 15      # max tool-call rounds for agentic loop (research needs more)

    def __init__(self, llm_bridge, desktop: DesktopControl, browser: BrowserAutomation,
                 llm_router=None, memory_store=None, continual_learner=None):
        self._llm = llm_bridge     # SmallModelBridge instance (fallback)
        self._llm_router = llm_router  # LLMRouter instance (Claude tool use)
        self._memory = memory_store    # VectorMemoryStore (for experience retrieval)
        self._continual = continual_learner  # ContinualLearner (learn_skill / learn_from_error)
        self._desktop = desktop
        self._browser = browser
        self._execution_history: List[Dict] = []
        self._session_context: List[str] = []   # tracks what happened this session
        self._last_page_text: str = ""          # latest page content for context
        self._last_page_url: str = ""           # latest URL visited
        self._cancel_event = threading.Event()
        self._pages_learned: set = set()        # URLs already learned from (dedup)
        self._exec_count: int = 0               # executions since last consolidation

        # Vision analyzer — see screenshots + images
        self._vision: Optional[VisionAnalyzer] = None
        if VISION_AVAILABLE:
            try:
                self._vision = VisionAnalyzer()
            except Exception:
                pass

        # Security kernel — auto-detect threats
        self._security = SecurityKernel() if SECURITY_AVAILABLE else None

        # Learn mode state
        self._learn_recording: Optional[List[Dict]] = None
        self._learn_workflow: Optional[Dict] = None

    # ─────────────────────────────────────────────
    #  Cancel / Stop
    # ─────────────────────────────────────────────

    def cancel(self):
        """Cancel the current execution immediately."""
        self._cancel_event.set()

    def _reset_cancel(self):
        """Reset cancel flag for new execution."""
        self._cancel_event.clear()

    # ─────────────────────────────────────────────
    #  Experience Memory — Learn from past executions
    # ─────────────────────────────────────────────

    def _retrieve_experience(self, message: str) -> str:
        """Retrieve past execution experience and user corrections.

        Searches procedural memory and user feedback for similar past tasks
        to help the agent learn from its mistakes and user feedback.
        """
        if not self._memory:
            return ""

        try:
            # 1. Check user_feedback.json for direct corrections
            feedback_path = os.path.join(os.path.dirname(__file__), "brain", "user_feedback.json")
            feedback_str = ""
            if os.path.exists(feedback_path):
                with open(feedback_path, "r") as f:
                    feedback = json.load(f)
                    # Find relevant corrections (simple match for this example)
                    for entry in feedback[-5:]:
                        feedback_str += f"- [CORRECTION]: {entry['learned_lesson']}\n"
            
            # 2. Search procedural memory
            results = self._memory.retrieve(
                query=message,
                collection="procedural",
                limit=3,
                min_relevance=0.4,
            )
            
            lines = []
            if feedback_str:
                lines.append("\n## CRITICAL LEARNED LESSONS (DO NOT REPEAT OLD MISTAKES):")
                lines.append(feedback_str)

            if results:
                lines.append("\n## PAST EXPERIENCE")
                for r in results:
                    lines.append(f"- [{r.relevance:.2f}] {r.content}")

            # Also check recent session context
            if self._session_context:
                lines.append("\nRecent actions this session:")
                for ctx in self._session_context[-5:]:
                    lines.append(f"- {ctx}")

            return "\n".join(lines) + "\n"
        except Exception:
            return ""

    def _auto_critique_and_learn(self, message: str, plan_intent: str, steps_detail: List[str], success: bool, result_summary: str):
        """Perform a deep 'Self-Critique' after every task to build local intelligence.
        
        This mimics Claude 4.6 Opus reasoning by forcing the agent to reflect on its own
        performance and extract 'Golden Traces' for local model fine-tuning.
        """
        if not success or not steps_detail:
            return

        try:
            # 1. Generate a 'Thinking Reflection' to explain the logic (Synthetic CoT)
            cot_explanation = (
                f"TASK ANALYSIS (Synthetic Chain of Thought):\n"
                f"GOAL: {message}\n"
                f"INTENT: {plan_intent}\n"
                f"RESULT: {result_summary[:500]}\n"
                f"REASONS FOR SUCCESS: The plan worked because I used the following logic sequence: "
                + " -> ".join([s.split(": ", 1)[0] for s in steps_detail])
            )
            
            # 2. Store as a 'Teacher' example for local Ollama models
            if self._memory:
                self._memory.store(
                    content=cot_explanation,
                    collection="procedural",
                    source="self_critique",
                    importance=0.8,
                    confidence=1.0,
                    metadata={"type": "golden_trace", "is_synthetic_cot": True}
                )
        except Exception:
            pass

    def _store_execution_experience(self, message: str, plan_intent: str,
                                     steps_detail: List[str], success: bool,
                                     failed_steps: List[str]):
        """Store structured execution experience in procedural memory.

        Unlike the old shallow logging, this stores:
        - What the user asked for
        - What steps worked (as a reusable skill)
        - What failed and why (as error patterns to avoid)
        """
        if not self._memory:
            return

        try:
            if success and steps_detail:
                # Store as a learned skill — "how to do X"
                skill_text = (
                    f"SKILL: {plan_intent}\n"
                    f"User said: {message[:200]}\n"
                    f"Steps that worked:\n" +
                    "\n".join(f"  {s}" for s in steps_detail[:10])
                )
                self._memory.store(
                    content=skill_text,
                    collection="procedural",
                    source="execution_skill",
                    importance=0.7,
                    confidence=0.9,
                    metadata={"type": "skill", "intent": plan_intent[:200]},
                )

            if failed_steps:
                # Store failures as error patterns to avoid
                error_text = (
                    f"ERROR PATTERN: {plan_intent}\n"
                    f"User said: {message[:200]}\n"
                    f"What failed:\n" +
                    "\n".join(f"  {s}" for s in failed_steps[:5])
                )
                self._memory.store(
                    content=error_text,
                    collection="procedural",
                    source="execution_error",
                    importance=0.6,
                    confidence=0.8,
                    metadata={"type": "error_pattern", "intent": plan_intent[:200]},
                )
        except Exception:
            pass

        # ── Auto-learn via ContinualLearner (free, no API) ──
        if success and steps_detail:
            self._auto_learn_skill(message, steps_detail)
            self._distill_to_local(message, steps_detail)
        if failed_steps:
            self._auto_learn_error(message, failed_steps)

    def _post_execution_learn(self, message: str, plan_intent: str,
                               steps_detail: List[str], success: bool,
                               failed_steps: List[str]):
        """Run ALL post-execution learning in one background thread.

        This is the master learning trigger — called once per execution:
        1. Store experience (skills + error patterns)
        2. Self-reflect (Claude evaluates performance)
        3. Curiosity harvest (learn related topics from Wikipedia)
        4. Consolidate memory (every 20 executions)
        """
        # Store experience (synchronous, fast)
        self._store_execution_experience(
            message, plan_intent, steps_detail, success, failed_steps,
        )

        # Everything else runs in a background thread
        def _background_learn():
            if steps_detail:
                self._self_reflect(message, steps_detail, failed_steps)
            if success and steps_detail:
                self._curiosity_harvest(message, steps_detail)
            self._maybe_consolidate()

        threading.Thread(target=_background_learn, daemon=True).start()

    def _self_reflect(self, message: str, steps_detail: List[str],
                      failed_steps: List[str]) -> Optional[str]:
        """Ask Claude to reflect on what went well/poorly and extract lessons.

        This is the self-improvement loop — after each task, the agent
        evaluates its own performance and stores insights for next time.
        Returns the reflection text (or None if unavailable).
        """
        if not self._has_claude_tools() or not steps_detail:
            return None

        reflection_prompt = (
            f"You just completed a task. Reflect briefly on what happened.\n\n"
            f"User request: {message[:300]}\n"
            f"Steps completed:\n" +
            "\n".join(f"  {s}" for s in steps_detail[:8]) +
            ("\n\nFailed steps:\n" + "\n".join(f"  {s}" for s in failed_steps[:3]) if failed_steps else "") +
            "\n\nIn 1-2 sentences: What worked well? What would you do differently next time? "
            "Be specific and actionable."
        )

        try:
            response = self._llm_router.chat(
                user_message=reflection_prompt,
                system="You are reflecting on your own task execution. Be brief and specific. Focus on actionable lessons.",
                provider="anthropic",
                max_tokens=150,
                temperature=0.1,
            )
            reflection = response.strip()
            if reflection and self._memory:
                self._memory.store(
                    content=f"REFLECTION: {message[:100]}\n{reflection}",
                    collection="procedural",
                    source="self_reflection",
                    importance=0.5,
                    confidence=0.85,
                    metadata={"type": "reflection"},
                )
            return reflection
        except Exception:
            return None

    # ─────────────────────────────────────────────
    #  Auto-learn: Wire ContinualLearner after executions
    # ─────────────────────────────────────────────

    def _auto_learn_skill(self, message: str, steps_detail: List[str]):
        """Automatically teach the ContinualLearner a new skill.

        This is the missing link — learn_skill() existed but was never
        called automatically. Now every successful execution teaches Jarvis
        a new skill that can be retrieved later. 100% free (no API call).
        """
        if not self._continual or not steps_detail:
            return
        try:
            # Extract a short skill name from the message
            skill_name = message[:80].strip()
            self._continual.learn_skill(
                skill_name=skill_name,
                description=f"How to: {message[:200]}",
                steps=[s.split(": ", 1)[-1] if ": " in s else s for s in steps_detail[:10]],
                examples=[message[:200]],
            )
        except Exception:
            pass

    def _auto_learn_error(self, message: str, failed_steps: List[str]):
        """Automatically teach ContinualLearner from errors.

        learn_from_error() existed but was never called automatically.
        Now every failure teaches Jarvis what NOT to do. 100% free.
        """
        if not self._continual or not failed_steps:
            return
        try:
            for failure in failed_steps[:3]:
                # Split "action: error_msg" format
                parts = failure.split(": ", 1)
                action = parts[0] if len(parts) > 1 else "unknown_action"
                error = parts[1] if len(parts) > 1 else failure
                self._continual.learn_from_error(
                    error_description=f"{action} failed: {error[:200]}",
                    solution=f"Try alternative approach for '{action}' when processing: {message[:100]}",
                    context=message[:200],
                )
        except Exception:
            pass

    # ─────────────────────────────────────────────
    #  Prompt Distillation: Claude teaches the Local Model
    # ─────────────────────────────────────────────

    def _distill_to_local(self, message: str, steps_detail: List[str]):
        """Store Claude's successful plans as few-shot examples for the local model.

        The idea: every time Claude (expensive) solves a task, we save the
        input→output mapping. Over time, the local Ollama model gets better
        because we prepend these examples to its prompts. Eventually, the
        local model handles most tasks and Claude is barely needed.

        This is FREE — just storing text in procedural memory.
        """
        if not self._memory or not steps_detail:
            return
        try:
            # Format as a distilled few-shot example
            example = (
                f"DISTILLED_EXAMPLE:\n"
                f"USER: {message[:300]}\n"
                f"PLAN:\n" +
                "\n".join(f"  {s}" for s in steps_detail[:8])
            )
            self._memory.store(
                content=example,
                collection="procedural",
                source="distillation",
                importance=0.65,
                confidence=0.9,
                metadata={"type": "distilled_example"},
            )
        except Exception:
            pass

    def _get_distilled_examples(self, message: str, limit: int = 2) -> str:
        """Retrieve distilled examples for the local model's prompt.

        Returns formatted few-shot examples from past Claude plans.
        """
        if not self._memory:
            return ""
        try:
            results = self._memory.retrieve(
                query=message,
                collection="procedural",
                limit=limit,
                min_relevance=0.5,
                where={"type": "distilled_example"},
            )
            if not results:
                return ""
            lines = ["## FEW-SHOT EXAMPLES (from past successful plans):"]
            for r in results:
                lines.append(r.content)
                lines.append("")
            return "\n".join(lines) + "\n"
        except Exception:
            return ""

    # ─────────────────────────────────────────────
    #  Local-First Agentic: Try Ollama before Claude
    # ─────────────────────────────────────────────

    def _try_local_agentic(self, message: str) -> Optional[ExecutionPlan]:
        """Try the FREE local Ollama model for planning before using Claude.

        Uses distilled examples (learned from past Claude plans) + experience
        memory to help the small model produce good plans. Over time, as more
        examples accumulate, this handles more and more tasks without Claude.

        Returns ExecutionPlan if local model produces a valid plan, None otherwise.
        """
        # Need enough distilled examples to be useful
        distilled = self._get_distilled_examples(message)
        experience = self._retrieve_experience(message)

        # Only try local if we have some context to help it
        if not distilled and not experience:
            return None

        local_prompt = (
            f"{distilled}"
            f"{experience}"
            f"\nNow plan for this new request:\n"
            f"USER: {message}\n\n"
            f"Respond with JSON: {{\"intent\": \"...\", \"steps\": [{{\"action\": \"...\", \"params\": {{...}}}}]}}\n"
            f"Available actions: open_in_chrome, google_search, goto, click, fill, "
            f"read_page, scroll, highlight, open_app, type_text, hotkey, run_command, "
            f"screenshot, answer_locally, wait, done.\n"
            f"Respond ONLY with JSON."
        )

        try:
            resp = self._llm.generate(
                prompt=local_prompt,
                system="You are an AI agent planner. Use the examples to plan tasks. Output only valid JSON.",
                max_tokens=400,
                temperature=0.0,
            )

            # Must be from a real provider (not fallback)
            if resp.provider in ("fallback", "memory_fallback"):
                return None

            plan = self._parse_plan(resp.content)
            if plan and plan.steps:
                plan.thinking = f"[Local model + distilled knowledge] {plan.thinking}"
                return plan
        except Exception:
            pass

        return None

    # ─────────────────────────────────────────────
    #  Autonomous External Learning: Learn from the World
    # ─────────────────────────────────────────────

    def _learn_from_page(self, url: str, content: str):
        """Auto-learn from any web page Jarvis visits during tasks.

        Every time Jarvis browses a page, it extracts knowledge and stores it.
        This runs in a background thread so it never slows down task execution.
        100% free — just local text processing + ChromaDB storage.
        """
        if not self._continual or not content or not url:
            return
        # Skip pages we already learned from this session
        if url in self._pages_learned:
            return
        # Skip tiny pages (nav-only, errors, etc.)
        if len(content) < 300:
            return
        # Skip non-content URLs
        skip_domains = ("google.com/search", "duckduckgo.com", "about:blank",
                        "chrome://", "localhost")
        if any(d in url for d in skip_domains):
            return

        self._pages_learned.add(url)
        try:
            # Infer topic from URL
            topic = self._topic_from_url(url)
            # Limit content to avoid huge storage
            self._continual.learn_from_web(
                url=url,
                content=content[:5000],
                topic=topic,
            )
        except Exception:
            pass

    def _learn_from_search_results(self, query: str, results: List[Dict]):
        """Extract knowledge from search results (DuckDuckGo/Google).

        When Jarvis searches the web, the snippets contain useful knowledge.
        Store them as semantic facts so Jarvis can answer questions offline later.
        """
        if not self._memory or not results:
            return
        try:
            facts = []
            for r in results[:5]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                if snippet and len(snippet) > 30:
                    facts.append(f"{title}: {snippet}")

            if facts:
                combined = f"Search: {query}\n" + "\n".join(facts)
                self._memory.store(
                    content=combined[:1500],
                    collection="semantic",
                    source="search_results",
                    importance=0.4,
                    confidence=0.6,
                    metadata={"type": "search_knowledge", "query": query[:200]},
                )
        except Exception:
            pass

    def _curiosity_harvest(self, message: str, steps_detail: List[str]):
        """After completing a task, proactively harvest related knowledge.

        The curiosity engine: Jarvis doesn't just do what you ask — it goes
        BEYOND by learning about related topics. If you asked about Python,
        it might also learn about pip, virtual environments, etc.

        Uses the local model (free) to generate 2-3 related topics,
        then harvests them from Wikipedia in the background.
        """
        if not self._continual or not self._memory:
            return

        try:
            # Use local model to identify what to learn more about
            resp = self._llm.generate(
                prompt=(
                    f"The user asked: {message[:200]}\n"
                    f"What was done: {'; '.join(s.split(': ', 1)[-1] for s in steps_detail[:4])}\n\n"
                    f"List 2-3 related topics worth learning about (one per line, just the topic name):"
                ),
                system="Output only topic names, one per line. Be specific and practical.",
                max_tokens=60,
                temperature=0.3,
            )

            if resp.provider in ("fallback", "memory_fallback"):
                return

            topics = [t.strip().strip("-•* ") for t in resp.content.strip().split("\n")
                      if t.strip() and len(t.strip()) > 2][:3]

            if not topics:
                return

            # Try to harvest from Wikipedia (lightweight, no browser needed)
            try:
                from src.knowledge.harvester import KnowledgeHarvester
                harvester = KnowledgeHarvester(vector_store=self._memory)
                for topic in topics:
                    try:
                        harvester.harvest_topic(topic, max_articles=1)
                    except Exception:
                        pass
            except ImportError:
                pass

        except Exception:
            pass

    def _maybe_consolidate(self):
        """Run memory consolidation every 20 executions.

        Keeps memory clean by merging duplicates and pruning weak entries.
        Runs in background thread to not block execution.
        """
        self._exec_count += 1
        if self._exec_count % 20 != 0:
            return
        if not self._continual:
            return
        try:
            threading.Thread(
                target=self._continual.consolidate,
                daemon=True,
            ).start()
        except Exception:
            pass

    @staticmethod
    def _topic_from_url(url: str) -> str:
        """Infer a topic category from a URL."""
        url_lower = url.lower()
        topic_hints = {
            "wikipedia": "encyclopedia", "stackoverflow": "programming",
            "github": "code", "youtube": "media", "arxiv": "research",
            "medium": "articles", "reddit": "discussion",
            "docs.python": "python", "developer.mozilla": "web_development",
            "amazon": "shopping", "netflix": "entertainment",
            "hianime": "anime", "crunchyroll": "anime",
        }
        for hint, topic in topic_hints.items():
            if hint in url_lower:
                return topic
        return "web"

    # ─────────────────────────────────────────────
    #  Confidence-Based Smart Routing
    # ─────────────────────────────────────────────

    def _plan_from_experience(self, message: str) -> Optional[ExecutionPlan]:
        """Skip the LLM entirely if we've done this task before (high confidence).

        Searches procedural memory for a very similar past skill (relevance > 0.8).
        If found, asks the LOCAL model (free, fast) to adapt the stored plan to
        the current request. This saves Claude API cost and is faster.

        Returns an ExecutionPlan if confident enough, None otherwise.
        """
        if not self._memory:
            return None

        try:
            results = self._memory.retrieve(
                query=message,
                collection="procedural",
                limit=1,
                min_relevance=0.8,
            )
            if not results:
                return None

            best = results[0]
            # Only use skill entries, not error patterns or reflections
            if not best.content.startswith("SKILL:"):
                return None

            # Use local model (free) to adapt the stored skill to current request
            adapt_prompt = (
                f"A similar task was completed before. Adapt it to the current request.\n\n"
                f"PAST SKILL:\n{best.content}\n\n"
                f"CURRENT REQUEST: {message}\n\n"
                f"Respond with a JSON plan. Format:\n"
                f'{{"intent": "...", "steps": [{{"action": "...", "params": {{...}}}}]}}\n'
                f"Available actions: open_in_chrome, google_search, goto, click, fill, "
                f"read_page, scroll, highlight, open_app, type_text, hotkey, run_command, "
                f"screenshot, answer_locally, wait, done.\n"
                f"Respond ONLY with the JSON."
            )

            resp = self._llm.generate(
                prompt=adapt_prompt,
                system="You adapt past execution plans to new requests. Output only valid JSON.",
                max_tokens=300,
                temperature=0.0,
            )

            if resp.provider in ("fallback", "memory_fallback"):
                return None

            plan = self._parse_plan(resp.content)
            if plan and plan.steps:
                plan.thinking = f"[Experience replay: {best.relevance:.0%} match] {plan.thinking}"
                return plan
        except Exception:
            pass

        return None

    # ─────────────────────────────────────────────
    #  Quick Intent Detection
    # ─────────────────────────────────────────────

    def needs_tools(self, message: str) -> bool:
        """Fast check: does this message need tool execution?"""
        # Speed optimization: obvious tool keywords → skip LLM call
        tool_signals = [
            "open ", "launch ", "start ", "go to ", "visit ", "browse ",
            "search ", "find ", "play ", "watch ", "download ", "install ",
            "run ", "execute ", "click ", "fill ", "type ", "screenshot",
            "close ", "kill ", "stop ", "navigate ", "show me ",
            "check ", "look up ", "google ", "youtube ", "take me to ",
            "book ", "order ", "buy ", "sign up ", "log in ", "login ",
            "research ", "analyze ", "explain how", "how to build",
            "what components", "what tools", "where to buy", "how can i",
            "tell me about", "give me detail", "find price",
            "see this ", "look at this", "check this ",
        ]
        msg_lower = message.lower().strip()
        for sig in tool_signals:
            if msg_lower.startswith(sig) or f" {sig}" in f" {msg_lower}":
                return True

        # Also check for URL patterns or app names
        if any(x in msg_lower for x in ["http://", "https://", "www.", ".com", ".org"]):
            return True

        # Research-related phrases (even without explicit keywords)
        research_phrases = [
            "how do they", "how are they", "what are they using",
            "what do i need", "where can i", "how much does",
            "i want to build", "i want to make", "send you link",
            "here is the link", "instagram.com", "youtube.com",
        ]
        for phrase in research_phrases:
            if phrase in msg_lower:
                return True

        # Default: CHAT (no extra LLM call — saves ~4 seconds)
        # The LLM classify was too slow for every single message
        return False

    # ─────────────────────────────────────────────
    #  Quick Plans (skip LLM for common patterns — instant speed)
    # ─────────────────────────────────────────────

    # ── Site aliases — maps fuzzy user names to real domains ──
    _SITE_ALIASES = {
        "hianime": "hianime.to", "hi anime": "hianime.to", "hi-anime": "hianime.to",
        "aniwatch": "aniwatch.to", "ani watch": "aniwatch.to",
        "9anime": "9anime.to", "9 anime": "9anime.to",
        "crunchyroll": "crunchyroll.com", "crunchy roll": "crunchyroll.com",
        "funimation": "funimation.com", "netflix": "netflix.com",
        "youtube": "youtube.com", "spotify": "spotify.com",
        "amazon": "amazon.com", "amazon prime": "primevideo.com",
        "prime video": "primevideo.com", "disney plus": "disneyplus.com",
        "disneyplus": "disneyplus.com", "disney+": "disneyplus.com",
        "hotstar": "hotstar.com", "jiocinema": "jiocinema.com",
        "hulu": "hulu.com", "twitch": "twitch.tv",
        "myanimelist": "myanimelist.net", "mal": "myanimelist.net",
        "gogoanime": "gogoanime3.co", "gogo anime": "gogoanime3.co",
        "zoro": "zoro.to", "animesuge": "animesuge.to",
        "vimeo": "vimeo.com", "dailymotion": "dailymotion.com",
    }

    # ── Noise phrases to strip from raw input ──
    _NOISE_PHRASES = [
        "right now", "right away", "immediately", "quickly", "fast",
        "for me", "online", "for free", "free", "in hd",
        "i can watch", "i could watch", "where i can watch",
        "or any website", "or any free website", "or any site",
        "or anything", "or whatever", "if possible", "asap",
        "scroll it", "check it", "scroll it check it",
        "click on it", "scroll down", "and check",
        "i want to", "i wanna", "i need to", "i'd like to",
        "can you", "could you", "please", "would you", "help me",
        "let me", "let's",
    ]

    def _extract_watch_intent(self, message: str) -> Optional[ExecutionPlan]:
        """Smart extraction for entertainment/watch requests.

        Handles messy multi-clause sentences like:
          'i want to watch anime right now online watch hi anime or any
           free website i can watch . anime name the darwin incident .
           scroll it check it'
        Extracts:  content='the darwin incident', site='hianime.to'
        """
        msg = message.lower().strip()

        # Quick check: does this look like a watch/stream request?
        watch_verbs = ("watch", "stream", "play", "listen", "view")
        if not any(v in msg for v in watch_verbs):
            return None

        # ── 1. Split into clauses (period, semicolon, " and then ") ──
        clauses = re.split(r'\s*[.;]\s*|\s+and then\s+|\s+then\s+', msg)
        clauses = [c.strip() for c in clauses if len(c.strip()) > 1]

        # ── 2. Strip noise phrases from the whole message ──
        cleaned = msg
        for noise in sorted(self._NOISE_PHRASES, key=len, reverse=True):
            cleaned = cleaned.replace(noise, " ")
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()

        # ── 3. Extract CONTENT NAME (the thing to watch) ──
        content_name = None

        # 3a. Explicit "name" patterns (highest priority):
        name_patterns = [
            # "anime name the darwin incident"
            r'(?:anime|movie|show|series|film|song|video|drama)\s+name\s+(?:is\s+)?(.+)',
            # "name of the anime is the darwin incident"
            r'name\s+of\s+(?:the\s+)?(?:anime|movie|show|series|film|song|video|drama)\s+(?:is\s+)?(.+)',
            # "the anime is the darwin incident"  /  "and the anime is X"
            r'(?:the|its|and\s+the)\s+(?:anime|movie|show|series|film|song|video|drama)\s+is\s+(?:called\s+)?(.+)',
            # "called / named / titled X"
            r'(?:called|named|titled)\s+(.+)',
            # "anime: the darwin incident"
            r'(?:anime|movie|show|series|film|song|video|drama)\s*:\s*(.+)',
        ]
        for pattern in name_patterns:
            for clause in clauses:
                m = re.search(pattern, clause)
                if m:
                    content_name = m.group(1).strip()
                    break
            if content_name:
                break

        # 3b. "watch X on Y" — extract X by finding known site boundary
        if not content_name:
            # Find where the site name starts in cleaned text
            for alias in sorted(self._SITE_ALIASES.keys(), key=len, reverse=True):
                idx = cleaned.find(alias)
                if idx > 0:
                    # Extract everything between the watch verb and the site alias
                    before = cleaned[:idx].strip()
                    m = re.search(r'(?:watch|stream|play|listen\s+to|view|see)\s+(.+?)(?:\s+on|\s+at|\s+from)?\s*$', before)
                    if m:
                        content_name = m.group(1).strip()
                        # Remove trailing "anime", "movie" etc if it's generic
                        content_name = re.sub(r'\s+(?:anime|movie|show|series|film|video)\s*$', '', content_name).strip()
                        # Remove LEADING generic: "anime the darwin incident" → "the darwin incident"
                        content_name = re.sub(r'^(?:anime|movie|show|series|film|video|the\s+anime|the\s+movie)\s+', '', content_name).strip()
                        if content_name and content_name not in ('anime', 'movie', 'show', 'series', 'film', 'the'):
                            break
                        content_name = None

        # 3c. Simple "watch/play X anime" / "X anime"
        if not content_name:
            m = re.search(r'(?:watch|stream|play)\s+(?:the\s+)?(.+?)\s+(?:anime|movie|show|series|film)\b', cleaned)
            if m and len(m.group(1).split()) <= 6:
                content_name = m.group(1).strip()

        # 3d. "watch X on Y" regex (handles simple cases)
        if not content_name:
            m = re.search(
                r'(?:watch|stream|play|listen\s+to|view|see)\s+(.+?)\s+(?:on|at|from)\s+\S',
                cleaned,
            )
            if m and len(m.group(1).split()) <= 8:
                content_name = m.group(1).strip()
                content_name = re.sub(r'\s+(?:anime|movie|show|series|film|video)\s*$', '', content_name).strip()
                # Also strip LEADING generic words: "anime the darwin incident" → "the darwin incident"
                content_name = re.sub(r'^(?:anime|movie|show|series|film|video|the\s+anime|the\s+movie)\s+', '', content_name).strip()
                if content_name in ('anime', 'movie', 'show', 'the', ''):
                    content_name = None

        # 3e. Simple "watch X" / "play X" (no site, no explicit name pattern)
        if not content_name:
            m = re.search(
                r'(?:watch|stream|play|listen\s+to)\s+(.+?)$',
                cleaned,
            )
            if m and len(m.group(1).split()) <= 6:
                content_name = m.group(1).strip()
                content_name = re.sub(r'\s+(?:anime|movie|show|series|film|video)\s*$', '', content_name).strip()
                if content_name in ('anime', 'movie', 'show', 'the', 'it', ''):
                    content_name = None

        # 3f. Look for a short clause that is just a title (no action verbs)
        if not content_name:
            action_words = {'watch', 'open', 'search', 'find', 'scroll', 'check',
                            'click', 'go', 'play', 'stream', 'visit', 'browse',
                            'or', 'any', 'website', 'site', 'free', 'i'}
            for clause in clauses:
                words = clause.split()
                if 1 <= len(words) <= 7 and not any(w in action_words for w in words):
                    content_name = clause
                    break

        # Clean content name — remove trailing noise
        if content_name:
            content_name = re.sub(
                r'\s+(?:scroll|check|click|open|and|then|it|online|free|hd|'
                r'subbed|dubbed|streaming|full|episode|eng sub|sub|dub)\b.*$',
                '', content_name,
            ).strip().rstrip('.')
            if not content_name:
                content_name = None

        # ── 4. Extract SITE (where to watch) ──
        site_domain = None
        # 4a. Check known aliases (longest first to avoid partial matches)
        all_text = ' | '.join(clauses) + ' | ' + cleaned
        for alias, domain in sorted(self._SITE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
            if alias in all_text:
                site_domain = domain
                break

        # 4b. Explicit domain in text: "crunchyroll.com"
        if not site_domain:
            dm = re.search(r'(\S+\.(?:com|org|net|io|to|tv|co|me|xyz|gg|app|dev|in))\b', msg)
            if dm:
                site_domain = dm.group(1)

        # ── 5. Build execution plan ──
        if not content_name and not site_domain:
            return None

        if content_name and site_domain:
            intent = f"Watch {content_name} on {site_domain}"
            steps = [
                Step(1, "open_in_chrome", {"url": f"https://{site_domain}"},
                     f"Chrome → {site_domain}"),
                Step(2, "open_in_chrome",
                     {"url": f"https://www.google.com/search?q={urllib.parse.quote_plus(content_name + ' ' + site_domain)}"},
                     f"Chrome → Search: {content_name} on {site_domain}"),
            ]
        elif content_name:
            search_q = f"{content_name} watch online"
            intent = f"Watch: {content_name}"
            steps = [
                Step(1, "open_in_chrome",
                     {"url": f"https://www.google.com/search?q={urllib.parse.quote_plus(search_q)}"},
                     f"Chrome → Watch: {content_name}"),
            ]
        else:
            intent = f"Open {site_domain}"
            steps = [
                Step(1, "open_in_chrome", {"url": f"https://{site_domain}"},
                     f"Chrome → {site_domain}"),
            ]

        return ExecutionPlan(
            intent=intent,
            needs_tools=True,
            thinking=f"Smart NLP → content='{content_name}', site='{site_domain}'",
            steps=steps,
        )

    def _try_quick_plan(self, message: str) -> Optional[ExecutionPlan]:
        """Pattern-match common requests → instant plan (no LLM call).

        Smart NLP pipeline:
        1. _extract_watch_intent() — handles complex multi-clause entertainment sentences
        2. Pattern matching — handles search, open, app, screenshot requests
        """
        msg = message.lower().strip()

        # ── 1. Try smart watch/entertainment extraction FIRST ──
        watch_plan = self._extract_watch_intent(message)
        if watch_plan:
            return watch_plan

        # Normalized: remove filler words for simpler pattern matching
        clean = re.sub(r'\b(please|can you|could you|i want to|i wanna|i need to|i\'d like to|would you|help me)\b', '', msg).strip()
        clean = re.sub(r'\s+', ' ', clean)

        # --- Question patterns → answer locally first ---
        question_prefixes = [
            "what is ", "what are ", "what was ", "what does ", "what do ",
            "who is ", "who are ", "who was ",
            "how to ", "how do ", "how does ", "how can ", "how much ", "how many ",
            "when is ", "when was ", "when did ", "when does ",
            "where is ", "where are ", "where was ", "where do ",
            "why is ", "why are ", "why do ", "why does ", "why did ",
            "can you explain ", "explain ", "tell me about ",
            "define ", "describe ", "meaning of ",
            "is it true ", "is there ", "are there ",
            "difference between ",
        ]
        is_question = msg.endswith("?") or any(msg.startswith(p) for p in question_prefixes)
        # Also detect embedded questions: "tell me what is X"
        if not is_question and any(f" {p}" in msg for p in ["what is ", "who is ", "how to "]):
            is_question = True
        if is_question:
            return ExecutionPlan(
                intent=f"Answer: {message[:80]}",
                needs_tools=True,
                thinking="Answering locally first, will search Chrome if unsure",
                steps=[
                    Step(1, "answer_locally", {"question": message},
                         f"Answer: {message[:60]}"),
                ],
            )

        # --- Extract website/domain if user specifies one ---
        url_match = re.search(r'(https?://[^\s,]+)', message)
        if url_match:
            url = url_match.group(1).rstrip('.')
            # Special handling for video/social links to force visual analysis
            is_video = any(x in url.lower() for x in ["instagram.com/reel/", "youtube.com/watch", "youtu.be/", "tiktok.com/"])
            
            if is_video:
                return ExecutionPlan(
                    intent=f"Analyze video: {url[:60]}",
                    needs_tools=True,
                    thinking="This is a video/reel. I must open it and use Vision to 'see' the content before researching.",
                    steps=[
                        Step(1, "open_in_chrome", {"url": url}, f"Open video: {url[:40]}"),
                        Step(2, "wait", {"seconds": 3}, "Wait for video to load"),
                        Step(3, "analyze_screenshot", {"target": "browser", "question": "What components, tools, or items are shown? Describe the building process."}, "Analyze video content"),
                        Step(4, "deep_research", {"topic": "components and build steps seen in video", "focus": "pricing, where to buy, how to make"}, "Research findings"),
                    ],
                )
            
            return ExecutionPlan(
                intent=f"Open URL: {url[:60]}",
                needs_tools=True,
                thinking=f"Directly opening the specified URL: {url}",
                steps=[
                    Step(1, "open_in_chrome", {"url": url}, f"Open: {url[:40]}"),
                ],
            )

        explicit_domain = re.search(r'(\S+\.(?:com|org|net|io|to|tv|co|me|xyz|gg|app|dev|in))\b', msg)

        # --- "Do X on Y website" pattern (general site + action) ---
        # "find wireless earbuds on amazon under 2000"
        # "search python tutorials on youtube"
        action_on_site = re.search(
            r'(?:search|find|look for|buy|order|get|browse|check)\s+(.+?)\s+(?:on|at|from|in)\s+(\S+)',
            clean
        )
        if action_on_site:
            query = action_on_site.group(1).strip()
            site_raw = action_on_site.group(2).strip().rstrip('.')
            site = site_raw.replace(" website", "").replace(" site", "").strip()
            if not re.search(r'\.\w{2,}$', site):
                site = site + ".com"
            search_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(query + ' site:' + site)}"
            return ExecutionPlan(
                intent=f"Search {query} on {site}",
                needs_tools=True,
                thinking=f"Searching '{query}' on {site}",
                steps=[
                    Step(1, "open_in_chrome", {"url": search_url},
                         f"Chrome → {query} on {site}"),
                ],
            )

        # --- Search patterns ---
        search_q = None
        for prefix in ["search for ", "search ", "google ", "look up ", "find me ",
                        "find ", "look for ", "what is the latest ", "latest ",
                        "search for the latest news about ", "search for the latest ",
                        "show me "]:
            if msg.startswith(prefix):
                search_q = message[len(prefix):].strip()
                for suffix in [" on google", " online", " on the internet", " on the web"]:
                    if search_q.lower().endswith(suffix):
                        search_q = search_q[:len(search_q)-len(suffix)].strip()
                break

        if search_q:
            google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(search_q)}"
            return ExecutionPlan(
                intent=f"Search: {search_q}",
                needs_tools=True,
                thinking=f"Opening Chrome → Google: '{search_q}'",
                steps=[
                    Step(1, "open_in_chrome", {"url": google_url},
                         f"Chrome → Google: {search_q}"),
                ],
            )

        # --- Open URL patterns ---
        url_match = re.search(r"(?:go to|open|visit|navigate to|take me to)\s+(https?://\S+|www\.\S+|\S+\.\w{2,}(?:/\S*)?)", msg)
        if url_match:
            url = url_match.group(1)
            if not url.startswith("http"):
                url = "https://" + url
            return ExecutionPlan(
                intent=f"Open {url}",
                needs_tools=True,
                thinking="Opening in Chrome",
                steps=[
                    Step(1, "open_in_chrome", {"url": url}, f"Chrome → {url}"),
                ],
            )

        # --- "Open X" where X might be a website (has a dot or known name) ---
        open_site = re.search(r'(?:open|go to|visit)\s+(.+?)(?:\s+website|\s+site|\s+page)?$', msg)
        if open_site:
            target = open_site.group(1).strip()
            known_sites = {
                "youtube": "https://youtube.com", "google": "https://google.com",
                "gmail": "https://gmail.com", "twitter": "https://twitter.com",
                "x": "https://x.com", "reddit": "https://reddit.com",
                "github": "https://github.com", "facebook": "https://facebook.com",
                "instagram": "https://instagram.com", "linkedin": "https://linkedin.com",
                "amazon": "https://amazon.com", "netflix": "https://netflix.com",
                "spotify": "https://spotify.com", "whatsapp": "https://web.whatsapp.com",
                "chatgpt": "https://chat.openai.com", "hianime": "https://hianime.to",
                "crunchyroll": "https://crunchyroll.com",
            }
            if target in known_sites:
                url = known_sites[target]
                return ExecutionPlan(
                    intent=f"Open {target}",
                    needs_tools=True,
                    thinking="Opening in Chrome",
                    steps=[Step(1, "open_in_chrome", {"url": url}, f"Chrome → {url}")],
                )

        # --- Open app patterns ---
        app_match = re.search(r"(?:open|launch|start|run)\s+(chrome|vscode|vs code|notepad|calculator|terminal|cmd|powershell|firefox|edge|word|excel|paint|file explorer|explorer|spotify|discord|slack|telegram|teams)", msg)
        if app_match:
            app = app_match.group(1)
            if app == "vs code":
                app = "vscode"
            return ExecutionPlan(
                intent=f"Open {app}",
                needs_tools=True,
                thinking="Direct app launch",
                steps=[Step(1, "open_app", {"name": app}, f"Open {app}")],
            )

        # --- Screenshot ---
        if "screenshot" in msg:
            if "desktop" in msg or "screen" in msg:
                return ExecutionPlan(
                    intent="Take desktop screenshot",
                    needs_tools=True, thinking="Screenshot",
                    steps=[Step(1, "screenshot_desktop", {}, "Screenshot desktop")],
                )
            return ExecutionPlan(
                intent="Take browser screenshot",
                needs_tools=True, thinking="Screenshot",
                steps=[Step(1, "screenshot_browser", {}, "Screenshot browser")],
            )

        # --- Catch-all: if explicit domain found, open it in Chrome ---
        if explicit_domain:
            domain = explicit_domain.group(1)
            url = f"https://{domain}"
            # Try to extract what user wants to do on that site
            return ExecutionPlan(
                intent=f"Open {domain}",
                needs_tools=True,
                thinking=f"Opening {domain} in Chrome",
                steps=[Step(1, "open_in_chrome", {"url": url}, f"Chrome → {domain}")],
            )

        return None  # No quick plan matched → use LLM

    # ─────────────────────────────────────────────
    #  Claude Native Tool-Use Planning
    # ─────────────────────────────────────────────

    def _has_claude_tools(self) -> bool:
        """Check if Claude tool calling is available."""
        if not self._llm_router or not LLM_ROUTER_AVAILABLE or not JARVIS_TOOLS:
            return False
        return "anthropic" in self._llm_router.providers

    def _plan_with_tools(self, message: str) -> Optional[ExecutionPlan]:
        """Use Claude native tool calling to create an execution plan.

        Instead of asking the LLM to output JSON text that we parse,
        we let Claude call tools directly via the Anthropic tool_use protocol.
        This is far more reliable than text-JSON parsing.

        Returns None if tool calling fails (falls back to text-JSON).
        """
        if not self._has_claude_tools():
            return None

        try:
            messages = [Message(Role.USER, message)]
            # If Claude fails, LLMRouter will automatically fall back to Gemini/Ollama
            # but native tool calling works best on Anthropic.
            response = self._llm_router.chat_with_tools(
                messages=messages,
                tools=JARVIS_TOOLS,
                system=TOOL_USE_SYSTEM,
                tool_choice="auto",
            )

            # If the LLM chose not to use tools (pure text response), it's a chat question
            if not response.tool_calls:
                return ExecutionPlan(
                    intent=message,
                    needs_tools=False,
                    thinking=response.content or "No tools needed — this is a chat question.",
                    steps=[],
                )

            # Convert ToolCalls → Steps
            steps = []
            for i, tc in enumerate(response.tool_calls):
                action = tc.name
                params = tc.arguments

                # Map the unified "screenshot" tool to specific actions
                if action == "screenshot":
                    target = params.get("target", "desktop")
                    action = "screenshot_desktop" if target == "desktop" else "screenshot_browser"
                    params = {}

                # "done" tool = no more execution needed
                if action == "done":
                    break

                steps.append(Step(
                    id=i + 1,
                    action=action,
                    params=params,
                    description=f"{action}({', '.join(f'{k}={v!r}' for k, v in params.items())})",
                ))

            return ExecutionPlan(
                intent=message,
                needs_tools=bool(steps),
                thinking=response.content or "Claude tool-use planning",
                steps=steps,
            )

        except Exception:
            return None  # Fall back to text-JSON planning

    # ─────────────────────────────────────────────
    #  Multi-Turn Agentic Loop (Claude decides next step)
    # ─────────────────────────────────────────────

    def run_agentic(self, message: str) -> Generator[Dict, None, None]:
        """Execute with Claude's native multi-turn tool calling + experience memory.

        Enhanced agentic loop:
          1. Retrieve past experience for similar tasks (experience memory)
          2. Claude sees user request + experience → calls a tool
          3. We execute the tool → feed result back as tool_result
          4. Claude sees the result → decides the next tool (or responds with text)
          5. Repeat until Claude says "done" or returns text (up to MAX_TOOL_ROUNDS)
          6. Store structured execution experience + self-reflect

        This is what makes Jarvis smarter than raw Claude:
        - It REMEMBERS what worked before (experience retrieval)
        - It LEARNS from every execution (experience storage)
        - It REFLECTS on its own performance (self-improvement)
        """
        if not self._has_claude_tools():
            yield {"type": "error", "content": "Claude tool calling unavailable — using fallback planning."}
            return

        self._reset_cancel()

        yield {"type": "thinking", "content": "Planning with Claude tool use..."}

        # ── Retrieve past experience for this type of task ──
        experience = self._retrieve_experience(message)
        system_prompt = TOOL_USE_SYSTEM
        if experience:
            system_prompt = TOOL_USE_SYSTEM + experience
            yield {"type": "observe", "content": "Retrieved past experience for similar tasks."}

        # Conversation history for the multi-turn loop
        messages = [Message(Role.USER, message)]
        completed_steps = 0
        step_results = []       # human-readable summaries
        failed_steps = []       # failed step details
        total_failed = 0

        for round_num in range(self.MAX_TOOL_ROUNDS):
            if self._cancel_event.is_set():
                yield {"type": "cancelled", "message": "Stopped by user"}
                return

            try:
                # If Claude fails, LLMRouter will automatically fall back to Gemini/Ollama
                response = self._llm_router.chat_with_tools(
                    messages=messages,
                    tools=JARVIS_TOOLS,
                    system=system_prompt,
                    tool_choice="auto",
                )
            except Exception as e:
                yield {"type": "error", "content": f"LLM Routing error: {str(e)[:200]}"}
                return

            # If the LLM responds with text only (no tool calls), we're done
            if not response.tool_calls:
                summary = response.content or f"Done! {completed_steps} steps completed."

                # ── Post-execution: learn from everything ──
                self._post_execution_learn(
                    message, message, step_results,
                    success=(total_failed == 0), failed_steps=failed_steps,
                )

                yield {
                    "type": "complete",
                    "summary": summary,
                    "steps_done": completed_steps,
                    "steps_total": completed_steps,
                    "steps_failed": total_failed,
                }
                # Proactive suggestions after agentic completion
                yield from self._generate_suggestions(message)
                return

            # Emit plan on first round
            if round_num == 0:
                yield {
                    "type": "plan",
                    "intent": message,
                    "thinking": response.content or "Claude tool-use planning",
                    "steps": [
                        {"id": i + 1, "action": tc.name, "description": str(tc.arguments), "status": "pending"}
                        for i, tc in enumerate(response.tool_calls)
                    ],
                }
            elif response.content:
                # On subsequent rounds, emit Claude's reasoning as an observe event
                yield {"type": "observe", "content": response.content[:500]}

            # Add Claude's response (with tool calls) to conversation history
            messages.append(Message(Role.ASSISTANT, response.content or ""))

            # Execute each tool call and feed results back
            for tc in response.tool_calls:
                action = tc.name
                params = tc.arguments

                # Handle "done" tool
                if action == "done":
                    summary = params.get("summary", f"Completed {completed_steps} steps.")

                    # ── Post-execution: learn from everything ──
                    self._post_execution_learn(
                        message, summary, step_results,
                        success=(total_failed == 0), failed_steps=failed_steps,
                    )

                    yield {
                        "type": "complete",
                        "summary": summary,
                        "steps_done": completed_steps,
                        "steps_total": completed_steps,
                        "steps_failed": total_failed,
                    }
                    return

                # Map screenshot tool
                if action == "screenshot":
                    target = params.get("target", "desktop")
                    action = "screenshot_desktop" if target == "desktop" else "screenshot_browser"
                    params = {}

                completed_steps += 1
                step = Step(id=completed_steps, action=action, params=params,
                            description=f"{action}({params})")

                yield {
                    "type": "step_start",
                    "step_id": completed_steps,
                    "action": action,
                    "description": step.description,
                }

                # Execute the step
                start_t = time.time()
                try:
                    result = self._execute_step(step)
                    duration = (time.time() - start_t) * 1000
                except Exception as e:
                    result = {"success": False, "error": str(e)[:300]}
                    duration = (time.time() - start_t) * 1000

                if result.get("success"):
                    detail = self._summarize_result(action, result)
                    yield {
                        "type": "step_done",
                        "step_id": completed_steps,
                        "success": True,
                        "detail": detail,
                        "duration_ms": round(duration),
                    }
                    step_results.append(f"Step {completed_steps} ({action}): {detail}")

                    # Observation events (same as execute_plan)
                    if action in ("open_browser", "goto", "google_search", "click"):
                        if result.get("url"):
                            yield {
                                "type": "tab_update",
                                "step_id": completed_steps,
                                "url": result.get("url", ""),
                                "title": result.get("title", ""),
                                "action": action,
                            }
                        self._observe_page()

                    if action == "read_page" and result.get("text"):
                        self._last_page_text = result["text"]
                        yield {
                            "type": "page_preview",
                            "step_id": completed_steps,
                            "url": result.get("url", ""),
                            "title": result.get("title", ""),
                            "snippet": result["text"][:500],
                        }

                    if action == "fast_search" and result.get("results"):
                        yield {
                            "type": "search_results",
                            "step_id": completed_steps,
                            "query": tc.arguments.get("query", ""),
                            "results": result["results"][:8],
                        }
                        # Auto-learn from search results (background, free)
                        threading.Thread(
                            target=self._learn_from_search_results,
                            args=(tc.arguments.get("query", ""), result["results"]),
                            daemon=True,
                        ).start()

                    # Research results — show findings in UI
                    if action == "deep_research" and result.get("report"):
                        yield {
                            "type": "observe",
                            "content": f"Research complete — {len(result.get('sources', []))} sources analyzed",
                        }

                    if action == "analyze_page" and result.get("analysis"):
                        yield {
                            "type": "observe",
                            "content": f"Page analyzed: {result['analysis'][:150]}...",
                        }

                    if action == "analyze_screenshot" and result.get("description"):
                        yield {
                            "type": "observe",
                            "content": f"Vision: {result['description'][:150]}...",
                        }
                else:
                    error = result.get("error", "unknown error")
                    total_failed += 1
                    yield {
                        "type": "step_failed",
                        "step_id": completed_steps,
                        "error": error[:300],
                        "duration_ms": round(duration),
                    }
                    step_results.append(f"Step {completed_steps} ({action}): FAILED - {error[:100]}")
                    failed_steps.append(f"{action}: {error[:150]}")

                # Feed tool result back to Claude so it can decide next step
                # Research tools get higher limits since they contain the actual findings
                max_result_size = 6000 if action in ("analyze_page", "deep_research", "analyze_screenshot", "read_page") else 2500
                result_text = json.dumps({
                    k: v for k, v in result.items()
                    if k != "raw" and isinstance(v, (str, int, float, bool, list))
                }, default=str)[:max_result_size]

                messages.append(Message(
                    role=Role.TOOL,
                    content=result_text,
                    tool_call_id=tc.id,
                ))

        # Exhausted all rounds — still learn from the execution
        self._post_execution_learn(
            message, message, step_results,
            success=(total_failed == 0), failed_steps=failed_steps,
        )
        yield {
            "type": "complete",
            "summary": f"Completed {completed_steps} steps (reached max rounds).",
            "steps_done": completed_steps,
            "steps_total": completed_steps,
            "steps_failed": total_failed,
        }

    # ─────────────────────────────────────────────
    #  Plan Creation
    # ─────────────────────────────────────────────

    def create_plan(self, message: str) -> ExecutionPlan:
        """Use the LLM to create an execution plan from natural language.

        Priority order (FREE first, expensive last):
          1. Quick NLP plan (0ms, regex patterns — common requests)
          2. Experience replay (skip all LLMs if done before — free, fast)
          3. Local model + distilled knowledge (Ollama, free forever)
          4. Claude native tool calling (if Anthropic available)
          5. Text-JSON fallback (any LLM via SmallModelBridge)
        """
        # 1. Try quick plan first (instant — no LLM)
        quick = self._try_quick_plan(message)
        if quick:
            quick.created_at = time.time()
            return quick

        # 2. Try experience replay (skip Claude for known tasks)
        exp_plan = self._plan_from_experience(message)
        if exp_plan:
            exp_plan.created_at = time.time()
            return self._enhance_plan(exp_plan) if exp_plan.needs_tools else exp_plan

        # 3. Try local model with distilled knowledge (FREE)
        local_plan = self._try_local_agentic(message)
        if local_plan:
            local_plan.created_at = time.time()
            return self._enhance_plan(local_plan) if local_plan.needs_tools else local_plan

        # 4. Try Claude native tool calling
        tool_plan = self._plan_with_tools(message)
        if tool_plan is not None:
            tool_plan.created_at = time.time()
            return self._enhance_plan(tool_plan) if tool_plan.needs_tools else tool_plan

        # 5. Text-JSON fallback (SmallModelBridge)
        start = time.time()

        resp = self._llm.generate(
            prompt=f"USER REQUEST: {message}",
            system=PLANNER_SYSTEM,
            max_tokens=512,
            temperature=0.0,
        )

        # If LLM is unavailable, fall back to chat mode (don't create broken plans)
        if resp.provider in ("fallback", "memory_fallback"):
            return ExecutionPlan(
                intent=message,
                needs_tools=False,
                thinking="LLM unavailable — switching to chat mode",
                steps=[],
            )

        plan = self._parse_plan(resp.content)
        plan = self._enhance_plan(plan)
        plan.created_at = time.time()
        return plan

    def _enhance_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """Post-process plan to fill gaps small models miss.
        
        Ensures read_page() follows search/navigation steps so the agent
        actually observes results instead of acting blindly.
        """
        if not plan.steps or not plan.needs_tools:
            return plan

        enhanced: List[Step] = []
        nav_actions = {"google_search", "open_browser", "click"}

        for step in plan.steps:
            enhanced.append(step)
            # If this is a navigation action and the NEXT step isn't already
            # wait or read_page, inject them
            next_action = None
            idx = plan.steps.index(step)
            if idx + 1 < len(plan.steps):
                next_action = plan.steps[idx + 1].action

            if step.action in nav_actions and next_action not in ("wait", "read_page"):
                enhanced.append(Step(
                    id=0, action="wait", params={"seconds": 2},
                    description="Wait for page to load",
                ))
                enhanced.append(Step(
                    id=0, action="read_page", params={},
                    description="Read page content to see results",
                ))

        # Re-number step IDs
        for i, s in enumerate(enhanced):
            s.id = i + 1

        plan.steps = enhanced
        return plan

    def _parse_plan(self, llm_output: str) -> ExecutionPlan:
        """Parse LLM JSON output into an ExecutionPlan."""
        # Extract JSON from LLM response (it might have extra text)
        json_str = llm_output.strip()

        # Try to find JSON block
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()
        
        # Find first { and last }
        start = json_str.find("{")
        end = json_str.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = json_str[start:end]

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError:
            # LLM gave bad JSON — make a simple plan from the text
            return ExecutionPlan(
                intent="execute user request",
                needs_tools=True,
                thinking=llm_output[:200],
                steps=[Step(
                    id=1, action="google_search",
                    params={"query": llm_output[:100]},
                    description="Search for what user wants",
                )],
            )

        steps = []
        for i, s in enumerate(data.get("steps", [])):
            steps.append(Step(
                id=i + 1,
                action=s.get("action", ""),
                params=s.get("params", {}),
                description=s.get("description", ""),
            ))

        return ExecutionPlan(
            intent=data.get("intent", ""),
            needs_tools=data.get("needs_tools", True),
            thinking=data.get("thinking", ""),
            steps=steps,
        )

    # ─────────────────────────────────────────────
    #  Plan Execution (with observation + self-correction)
    # ─────────────────────────────────────────────

    def execute_plan(self, plan: ExecutionPlan) -> Generator[Dict, None, None]:
        """
        Execute a plan step by step with OBSERVATION and SELF-CORRECTION.
        
        Unlike a simple linear executor, this:
        1. Executes each step
        2. OBSERVES the result (reads page content after navigation)
        3. If a step FAILS, asks LLM to replan and retries
        4. Tracks context so later steps can use earlier results
        5. After all steps, checks if goal was achieved
        
        Yields events:
          {"type": "plan", "intent": "...", "steps": [...], "thinking": "..."}
          {"type": "step_start", "step_id": 1, "action": "...", "description": "..."}
          {"type": "step_done", "step_id": 1, "success": True, "detail": "..."}
          {"type": "step_failed", "step_id": 1, "error": "..."}
          {"type": "observe", "content": "..."}
          {"type": "replan", "reason": "...", "new_steps": [...]}
          {"type": "complete", "summary": "...", "steps_done": 3, "steps_total": 5}
        """
        # Emit the plan
        yield {
            "type": "plan",
            "intent": plan.intent,
            "thinking": plan.thinking,
            "steps": [
                {"id": s.id, "action": s.action, "description": s.description, "status": "pending"}
                for s in plan.steps
            ],
        }

        completed = 0
        failed = 0
        step_results = []  # track results for context

        for step in plan.steps:
            # Check for user cancellation
            if self._cancel_event.is_set():
                yield {"type": "cancelled", "message": "Stopped by user"}
                return

            if step.action == "DONE":
                break

            # Emit step start
            yield {
                "type": "step_start",
                "step_id": step.id,
                "action": step.action,
                "description": step.description,
            }

            # Execute with retry on failure
            result = None
            start_t = time.time()
            step.status = "running"

            for attempt in range(1, self.MAX_RETRIES_PER_STEP + 1):
                try:
                    result = self._execute_step(step)
                    step.duration_ms = (time.time() - start_t) * 1000

                    if result.get("success"):
                        step.status = "done"
                        step.result = result
                        completed += 1
                        break
                    else:
                        # Tool returned success=False — treat as soft failure
                        err = result.get("error", "unknown error")
                        if attempt < self.MAX_RETRIES_PER_STEP:
                            # Try replanning this step
                            yield {
                                "type": "observe",
                                "content": f"Step failed: {err}. Adapting approach (attempt {attempt + 1})...",
                            }
                            new_plan = self._replan_single_step(plan, step, err)
                            if new_plan and new_plan.steps:
                                new_step = new_plan.steps[0]
                                step.action = new_step.action
                                step.params = new_step.params
                                step.description = new_step.description
                                yield {
                                    "type": "replan",
                                    "reason": err,
                                    "new_steps": [{"action": new_step.action, "description": new_step.description}],
                                }
                                continue
                        step.status = "failed"
                        step.error = err
                        failed += 1
                        break

                except Exception as e:
                    step.duration_ms = (time.time() - start_t) * 1000
                    err = str(e)
                    if attempt < self.MAX_RETRIES_PER_STEP:
                        yield {
                            "type": "observe",
                            "content": f"Error: {err[:200]}. Adapting approach...",
                        }
                        new_plan = self._replan_single_step(plan, step, err)
                        if new_plan and new_plan.steps:
                            new_step = new_plan.steps[0]
                            step.action = new_step.action
                            step.params = new_step.params
                            step.description = new_step.description
                            yield {
                                "type": "replan",
                                "reason": err[:200],
                                "new_steps": [{"action": new_step.action, "description": new_step.description}],
                            }
                            continue
                    step.status = "failed"
                    step.error = err
                    failed += 1
                    break

            # Emit result
            if step.status == "done":
                detail = self._summarize_result(step.action, result)
                yield {
                    "type": "step_done",
                    "step_id": step.id,
                    "success": True,
                    "detail": detail,
                    "duration_ms": round(step.duration_ms),
                }
                step_results.append(f"Step {step.id} ({step.action}): {detail}")

                # === OBSERVATION PHASE ===
                # After navigation actions, observe the page to build context
                if step.action in ("open_browser", "goto", "google_search", "click"):
                    if result.get("success"):
                        yield {
                            "type": "tab_update",
                            "step_id": step.id,
                            "url": result.get("url", ""),
                            "title": result.get("title", ""),
                            "action": step.action,
                        }
                        # Auto-observe: grab page context for smarter decisions
                        self._observe_page()

                if step.action == "get_links" and result.get("success"):
                    links = result.get("links", [])
                    if links:
                        yield {
                            "type": "recommendations",
                            "step_id": step.id,
                            "items": [
                                {"text": l.get("text", l.get("href", ""))[:80],
                                 "url": l.get("href", "")}
                                for l in links[:10]
                                if isinstance(l, dict) and l.get("href")
                            ],
                        }

                if step.action == "read_page" and result.get("success"):
                    text = result.get("text", "")
                    if text:
                        self._last_page_text = text
                        yield {
                            "type": "page_preview",
                            "step_id": step.id,
                            "url": result.get("url", ""),
                            "title": result.get("title", ""),
                            "snippet": text[:500],
                        }

                # === FAST SEARCH RESULTS ===
                if step.action == "fast_search" and result.get("success"):
                    items = result.get("results", [])
                    if items:
                        yield {
                            "type": "search_results",
                            "step_id": step.id,
                            "query": step.params.get("query", ""),
                            "results": items[:8],
                        }
                        # Store for context
                        summaries = [f"- {r['title']}: {r['snippet'][:80]}" for r in items[:5]]
                        self._last_page_text = "\n".join(summaries)
                        self._session_context.append(f"Searched: {step.params.get('query','')} → {len(items)} results")

                        # Auto-learn from search results (background, free)
                        threading.Thread(
                            target=self._learn_from_search_results,
                            args=(step.params.get("query", ""), items),
                            daemon=True,
                        ).start()

                # Research tool observations
                if step.action == "deep_research" and result.get("success"):
                    report = result.get("report", "")
                    if report:
                        self._last_page_text = report[:3000]
                        self._session_context.append(f"Researched: {step.params.get('topic','')} → {len(result.get('sources',[]))} sources")

                if step.action == "analyze_page" and result.get("success"):
                    analysis = result.get("analysis", "")
                    if analysis:
                        self._last_page_text = analysis[:3000]

                if step.action == "analyze_screenshot" and result.get("success"):
                    desc = result.get("description", "")
                    if desc:
                        self._session_context.append(f"Vision: {desc[:200]}")

            elif step.status == "failed":
                yield {
                    "type": "step_failed",
                    "step_id": step.id,
                    "error": step.error[:300],
                    "duration_ms": round(step.duration_ms),
                }
                step_results.append(f"Step {step.id} ({step.action}): FAILED - {step.error[:100]}")

        total = len([s for s in plan.steps if s.action != "DONE"])

        # === VERIFICATION PHASE ===
        # After all steps, briefly check if more work is needed
        verification = self._verify_completion(plan, step_results, completed, total)
        
        yield {
            "type": "complete",
            "summary": f"Done! {completed}/{total} steps completed." + (f" {verification}" if verification else ""),
            "steps_done": completed,
            "steps_total": total,
            "steps_failed": failed,
        }

        # Store in history for learning
        self._execution_history.append({
            "intent": plan.intent,
            "steps": total,
            "completed": completed,
            "failed": failed,
            "context": step_results[-3:],
            "timestamp": time.time(),
        })

        # Track in session
        self._session_context.append(f"Task: {plan.intent} → {completed}/{total} steps done")

    def _observe_page(self):
        """Silently observe current page state for context awareness + auto-learning.
        
        Now also learns from every page visited — knowledge extracted in background.
        """
        try:
            r = self._browser.read_page()
            if r.success and r.data:
                self._last_page_text = r.data[:3000]
                self._last_page_url = r.url or ""

                # Auto-learn from this page (background, non-blocking, free)
                if len(r.data) > 300 and r.url:
                    threading.Thread(
                        target=self._learn_from_page,
                        args=(r.url, r.data),
                        daemon=True,
                    ).start()
        except Exception:
            pass

    # ─────────────────────────────────────────────
    #  Security Gate
    # ─────────────────────────────────────────────

    def _check_security(self, tool: str, command: str, params: Dict = None) -> Optional[Dict]:
        """Pre-execution security check. Returns blocked dict if action should not proceed."""
        params = params or {}

        # Always block dangerous shell commands regardless of security kernel
        cmd_text = params.get("command", "") or ""
        for pattern in BLOCKED_COMMANDS:
            if re.search(pattern, cmd_text, re.IGNORECASE):
                return {
                    "success": False, "blocked": True,
                    "error": f"SECURITY: Command blocked — matches dangerous pattern",
                    "threat": "critical",
                }

        # URLs: only block truly dangerous ones, not unknown entertainment sites
        url = params.get("url", "")
        if url:
            from urllib.parse import urlparse
            try:
                parsed = urlparse(url)
                domain = parsed.netloc.lower().replace("www.", "")
                # Block obviously dangerous URLs (data:, javascript:, file:)
                if parsed.scheme in ("javascript", "data", "vbscript"):
                    return {
                        "success": False, "blocked": True,
                        "error": "SECURITY: Dangerous URL scheme blocked",
                        "threat": "critical",
                    }
            except Exception:
                pass

        # Use full SecurityKernel if available — map tool names correctly
        if self._security:
            try:
                mapped_tool = _TOOL_NAME_MAP.get(tool, tool)
                sec = self._security.check_action(mapped_tool, command, params)
                if sec.verdict == ActionVerdict.BLOCK:
                    return {
                        "success": False, "blocked": True,
                        "error": f"SECURITY: {sec.reason}",
                        "threat": sec.threat_level.value,
                    }
                if sec.verdict == ActionVerdict.FREEZE:
                    return {
                        "success": False, "blocked": True,
                        "error": f"SECURITY FREEZE: {sec.reason}. All operations halted.",
                        "threat": "critical",
                    }
            except Exception:
                pass

        return None  # Allowed

    def _is_safe_url(self, url: str) -> bool:
        """Quick check if a URL is from a known-safe domain."""
        try:
            from urllib.parse import urlparse
            domain = urlparse(url).netloc.lower().replace("www.", "")
            return domain in SAFE_DOMAINS
        except Exception:
            return False

    # ─────────────────────────────────────────────
    #  Learn Mode — Record → Analyze → Replay
    # ─────────────────────────────────────────────

    def start_learn_recording(self) -> Dict:
        """Start recording user actions via pynput."""
        try:
            from src.tools.desktop_control import ActionRecorder
            self._recorder = ActionRecorder()
            self._recorder.start()
            return {"success": True, "message": "Recording started — do your thing!"}
        except ImportError:
            return {"success": False, "error": "pynput not installed. Run: pip install pynput"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_learn_recording(self) -> Dict:
        """Stop recording and return summarized actions."""
        if not hasattr(self, '_recorder') or not self._recorder:
            return {"success": False, "error": "No recording in progress"}
        try:
            actions = self._recorder.stop()
            self._learn_recording = actions
            summary = self._summarize_recording(actions)
            return {"success": True, "actions_count": len(actions), "summary": summary}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _summarize_recording(self, actions: List[Dict]) -> str:
        """Create a human-readable summary of recorded actions."""
        if not actions:
            return "No actions recorded."
        lines = []
        for a in actions[:30]:
            t = a.get("type", "?")
            if t == "click":
                lines.append(f"Click at ({a.get('x',0)}, {a.get('y',0)}) in {a.get('window','?')}")
            elif t == "type":
                text = a.get("text", "")
                lines.append(f"Typed: {text[:50]}{'...' if len(text)>50 else ''}")
            elif t == "hotkey":
                lines.append(f"Pressed: {a.get('keys','?')}")
            elif t == "scroll":
                lines.append(f"Scrolled {a.get('direction','?')} in {a.get('window','?')}")
        return "\n".join(lines) if lines else "No meaningful actions."

    def analyze_recording(self) -> Dict:
        """Use LLM to understand the intent behind recorded actions."""
        if not self._learn_recording:
            return {"success": False, "error": "No recording to analyze"}
        summary = self._summarize_recording(self._learn_recording)
        try:
            resp = self._llm.generate(
                prompt=f"The user performed these actions on their computer:\n\n{summary}\n\nDescribe what the user was trying to accomplish as a high-level workflow with numbered steps. Be specific about the goal and the pattern they followed.",
                system="You analyze user behavior recordings and extract the workflow pattern. Describe the high-level intent and steps, not the raw clicks. Example: '1. Opened Instagram 2. Found a car reel 3. Copied reel link 4. Opened downloader site 5. Pasted link 6. Downloaded video 7. Created new post with downloaded video'",
                max_tokens=400,
                temperature=0.2,
            )
            workflow = resp.content.strip()
            self._learn_workflow = {
                "raw_actions": self._learn_recording,
                "workflow": workflow,
                "analyzed_at": time.time(),
            }
            return {"success": True, "workflow": workflow}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def replay_workflow(self, preferences: str = "") -> Generator[Dict, None, None]:
        """Intelligently replay the learned workflow with adaptations."""
        if not self._learn_workflow:
            yield {"type": "error", "content": "No workflow analyzed yet. Record and analyze first."}
            return
        workflow = self._learn_workflow.get("workflow", "")
        prompt = f"Convert this workflow into an execution plan:\n\n{workflow}"
        if preferences:
            prompt += f"\n\nUser preferences: {preferences}"
        prompt += "\n\nIMPORTANT: Don't blindly repeat the exact same URLs or content. Use your intelligence to find SIMILAR content that matches the user's interests. Ask user before committing to any posting or downloading action."

        yield {"type": "thinking", "content": "Analyzing workflow and creating intelligent replay plan..."}
        plan = self.create_plan(prompt)
        if plan.needs_tools and plan.steps:
            yield from self.execute_plan(plan)
        else:
            yield {"type": "chat_mode", "content": workflow}

    def _replan_single_step(self, original_plan: ExecutionPlan, failed_step: Step, error: str) -> Optional[ExecutionPlan]:
        """Ask LLM for an alternative approach for a failed step."""
        prompt = f"""A step in my plan failed. I need an alternative approach.

Original goal: {original_plan.intent}
Failed step: {failed_step.action}({json.dumps(failed_step.params)})
Error: {error}
Current page: {self._last_page_url}
Page content (first 500 chars): {self._last_page_text[:500]}

Give me ONE alternative step to try instead. Same JSON format as before."""

        try:
            resp = self._llm.generate(
                prompt=prompt,
                system=PLANNER_SYSTEM,
                max_tokens=256,
                temperature=0.1,
            )
            if resp.provider in ("fallback", "memory_fallback"):
                return None
            return self._parse_plan(resp.content)
        except Exception:
            return None

    def _verify_completion(self, plan: ExecutionPlan, results: List[str], completed: int, total: int) -> str:
        """Quick check: did we achieve the goal? Returns a short note or empty string."""
        if completed == 0:
            return "Could not complete the task — all steps failed."
        if completed < total and total > 1:
            return f"Partial completion — {total - completed} steps had issues."
        return ""

    def _execute_step(self, step: Step) -> Dict:
        """Execute a single step using the appropriate tool."""
        action = step.action
        params = step.params

        if action == "open_browser" or action == "goto":
            url = params.get("url", "")
            if url:
                # Fix malformed double-https/double-slash URLs
                url = re.sub(r'https?://+(https?://)', r'\1', url)
                if not url.startswith("http"):
                    url = "https://" + url
            r = self._browser.goto(url)
            return {"success": r.success, "url": r.url, "title": r.title, "error": r.error}

        elif action == "google_search":
            query = params.get("query", "")
            r = self._browser.google_search(query)
            time.sleep(1)  # let results load
            return {"success": r.success, "url": r.url, "title": r.title, "error": r.error}

        elif action == "fast_search":
            query = params.get("query", "")
            r = self._browser.fast_search(query)
            if r.success and isinstance(r.data, list):
                return {"success": True, "results": r.data,
                        "count": len(r.data), "duration_ms": r.duration_ms}
            return {"success": r.success, "error": r.error, "results": []}

        elif action == "open_in_chrome":
            url = params.get("url", "")
            if url:
                # Fix malformed double-https/double-slash URLs
                url = re.sub(r'https?://+(https?://)', r'\1', url)
                if not url.startswith("http"):
                    url = "https://" + url
            # Chrome is user-visible — never block it. User can see the URL.
            r = self._desktop.open_url_in_browser(url)
            return {"success": r.success, "url": url, "detail": r.detail, "error": r.error}

        elif action == "answer_locally":
            question = params.get("question", "")
            try:
                resp = self._llm.generate(
                    prompt=question,
                    system="You are a helpful assistant. Answer the question clearly and concisely in 2-4 sentences. If you are not sure about the answer, say 'I\'m not certain' at the start.",
                    max_tokens=300,
                    temperature=0.3,
                )
                answer = resp.content.strip()
                is_unsure = any(x in answer.lower()[:60] for x in [
                    "i'm not certain", "i'm not sure", "i don't know",
                    "i cannot", "i can't", "as an ai",
                ])
                if is_unsure or resp.provider in ("fallback", "memory_fallback"):
                    # Fall back to Chrome search
                    google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(question)}"
                    self._desktop.open_url_in_browser(google_url)
                    return {
                        "success": True, "answer": answer,
                        "source": "local+chrome", "url": google_url,
                        "detail": f"Opened Chrome for more details",
                    }
                return {
                    "success": True, "answer": answer,
                    "source": "local", "detail": "Answered locally",
                }
            except Exception as e:
                google_url = f"https://www.google.com/search?q={urllib.parse.quote_plus(question)}"
                self._desktop.open_url_in_browser(google_url)
                return {"success": True, "source": "chrome", "url": google_url,
                        "detail": "Searching Chrome", "error": str(e)}

        elif action == "scroll":
            direction = params.get("direction", "down")
            amount = int(params.get("amount", 500))
            r = self._browser.scroll(direction, amount)
            return {"success": r.success, "error": r.error}

        elif action == "highlight":
            target = params.get("target", params.get("selector", params.get("text", "")))
            r = self._browser.highlight_on_page(target)
            return {"success": r.success, "found": r.data, "error": r.error}

        elif action == "click":
            selector = params.get("selector", "")
            # Try text-based click first (more natural for LLM)
            r = self._smart_click(selector)
            time.sleep(1)
            return {"success": r.success, "error": r.error}

        elif action == "fill":
            selector = params.get("selector", "")
            value = params.get("value", "")
            r = self._browser.fill(selector, value)
            return {"success": r.success, "error": r.error}

        elif action == "read_page":
            r = self._browser.read_page()
            text = r.data[:8000] if r.data else ""
            return {"success": r.success, "text": text, "url": r.url, "title": r.title}

        elif action == "get_links":
            r = self._browser.get_links()
            links = r.data[:30] if r.data else []
            return {"success": r.success, "links": links}

        elif action == "screenshot_browser":
            r = self._browser.screenshot()
            return {"success": r.success, "path": r.screenshot_path}

        elif action == "open_app":
            name = params.get("name", "")
            r = self._desktop.open_app(name)
            return {"success": r.success, "detail": r.detail, "error": r.error}

        elif action == "close_app":
            name = params.get("name", "")
            r = self._desktop.close_app(name)
            return {"success": r.success, "detail": r.detail, "error": r.error}

        elif action == "run_command":
            cmd = params.get("command", "")
            sec = self._check_security("desktop", "run_command", {"command": cmd})
            if sec and sec.get("blocked"):
                return sec
            r = self._desktop.run_command(cmd, timeout=30)
            return {"success": r.success, "output": r.detail[:2000], "error": r.error}

        elif action == "screenshot_desktop":
            r = self._desktop.screenshot()
            return {"success": r.success, "path": r.screenshot_path}

        elif action == "type_text":
            text = params.get("text", "")
            r = self._desktop.type_unicode(text)
            return {"success": r.success, "error": r.error}

        elif action == "hotkey":
            keys = params.get("keys", "")
            if isinstance(keys, str):
                keys = [k.strip() for k in keys.split("+")]
            r = self._desktop.hotkey(*keys)
            return {"success": r.success, "error": r.error}

        elif action == "system_info":
            info = self._desktop.get_system_info()
            return {"success": True, "info": info}

        elif action == "wait":
            secs = min(float(params.get("seconds", 2)), 10)  # cap at 10s
            time.sleep(secs)
            return {"success": True, "waited": secs}

        elif action == "analyze_page":
            question = params.get("question", "What is on this page?")
            r = self._browser.read_page()
            page_text = r.data[:8000] if r.data else ""
            if not page_text:
                return {"success": False, "error": "No page content to analyze"}
            # Use LLM to extract specific info from the page
            analysis_prompt = (
                f"Page URL: {r.url or 'unknown'}\n"
                f"Page Title: {r.title or 'unknown'}\n\n"
                f"Page Content:\n{page_text}\n\n"
                f"QUESTION: {question}\n\n"
                f"Give a detailed, specific answer based ONLY on the page content above. "
                f"Include names, numbers, prices, links, and specific details."
            )
            resp = self._llm.generate(
                prompt=analysis_prompt,
                system="You are a research assistant. Extract and summarize specific information from web page content. Be detailed and factual.",
                max_tokens=1500,
                temperature=0.1,
            )
            return {"success": True, "analysis": resp.content[:4000], "url": r.url, "title": r.title}

        elif action == "deep_research":
            topic = params.get("topic", "")
            focus = params.get("focus", "general overview")
            return self._deep_research(topic, focus)

        elif action == "analyze_screenshot":
            target = params.get("target", "browser")
            question = params.get("question", "Describe everything you see in detail.")
            return self._analyze_screenshot(target, question)

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _smart_click(self, selector_or_text: str) -> BrowserResult:
        """
        Intelligently click — handles CSS selectors AND natural text.
        If it looks like a CSS selector, use it directly.
        If it's text, find the link/button with that text.
        """
        s = selector_or_text.strip()

        # Looks like CSS selector
        if s.startswith(("#", ".", "[")) or "::" in s or ">" in s:
            return self._browser.click(s)

        # Text-based: try to find link/button with this text
        try:
            page = self._browser._page
            if page:
                # Try link with text
                loc = page.get_by_role("link", name=s)
                if loc.count() > 0:
                    loc.first.click(timeout=5000)
                    return BrowserResult(success=True, action="click", data=s)

                # Try button with text
                loc = page.get_by_role("button", name=s)
                if loc.count() > 0:
                    loc.first.click(timeout=5000)
                    return BrowserResult(success=True, action="click", data=s)

                # Try any element with text
                loc = page.get_by_text(s, exact=False)
                if loc.count() > 0:
                    loc.first.click(timeout=5000)
                    return BrowserResult(success=True, action="click", data=s)
        except Exception:
            pass

        # Fallback to raw selector
        return self._browser.click(s)

    # ─────────────────────────────────────────────
    #  Deep Research — multi-source search + read + synthesize
    # ─────────────────────────────────────────────

    def _deep_research(self, topic: str, focus: str = "general") -> Dict:
        """Research a topic thoroughly: search → read multiple pages → synthesize.
        
        This is the key tool that makes Jarvis actually research instead of just
        opening tabs. It searches multiple queries, reads top results, and compiles
        a detailed report using the LLM.
        """
        all_findings = []
        sources_used = []

        # Generate 2-3 search queries for comprehensive coverage
        queries = [f"{topic} {focus}"]
        if "price" in focus.lower() or "buy" in focus.lower() or "cost" in focus.lower():
            queries.append(f"{topic} price buy online")
        if "build" in focus.lower() or "how" in focus.lower() or "tutorial" in focus.lower():
            queries.append(f"{topic} tutorial step by step guide")
        if "component" in focus.lower() or "tool" in focus.lower() or "part" in focus.lower():
            queries.append(f"{topic} components tools parts list")

        # Search and read for each query
        for query in queries[:3]:
            try:
                # Use fast_search for structured results
                r = self._browser.fast_search(query)
                if not r.success or not r.data:
                    continue

                results = r.data[:5] if isinstance(r.data, list) else []

                # Read top 2 results for this query
                for item in results[:2]:
                    url = item.get("url", "") if isinstance(item, dict) else ""
                    title = item.get("title", "") if isinstance(item, dict) else ""
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if not url:
                        if snippet:
                            all_findings.append(f"[Search: {query}] {snippet}")
                        continue

                    # Read the page content
                    try:
                        pr = self._browser.goto(url)
                        if pr.success:
                            time.sleep(1)
                            page_r = self._browser.read_page()
                            if page_r.success and page_r.data and len(page_r.data) > 100:
                                page_text = page_r.data[:6000]
                                all_findings.append(
                                    f"[Source: {title or url}]\n{page_text}"
                                )
                                sources_used.append({"title": title, "url": url})
                                # Auto-learn in background
                                if url not in self._pages_learned:
                                    self._pages_learned.add(url)
                                    threading.Thread(
                                        target=self._learn_from_page,
                                        args=(url, page_r.data),
                                        daemon=True,
                                    ).start()
                    except Exception:
                        pass

                    # Also grab the snippet even if page read fails
                    if snippet:
                        all_findings.append(f"[Snippet: {title}] {snippet}")

            except Exception:
                continue

        if not all_findings:
            return {"success": False, "error": f"Could not find information about: {topic}"}

        # Synthesize all findings into a comprehensive report
        combined = "\n\n".join(all_findings)[:15000]
        synthesis_prompt = (
            f"RESEARCH TOPIC: {topic}\n"
            f"FOCUS: {focus}\n\n"
            f"RAW FINDINGS FROM MULTIPLE SOURCES:\n{combined}\n\n"
            f"TASK: Compile a detailed, well-organized research report based on the findings above.\n"
            f"Include:\n"
            f"- Key facts and details\n"
            f"- Specific names, numbers, prices (if available)\n"
            f"- Step-by-step instructions (if applicable)\n"
            f"- Where to buy/find things (if applicable)\n"
            f"- Practical tips and recommendations\n"
            f"Format the response clearly with sections and bullet points."
        )

        resp = self._llm.generate(
            prompt=synthesis_prompt,
            system="You are an expert research analyst. Synthesize multiple sources into a clear, detailed, actionable report. Include specific details, prices, links, and practical advice.",
            max_tokens=2000,
            temperature=0.1,
        )

        report = resp.content[:5000] if resp.content else "Research completed but synthesis failed."

        return {
            "success": True,
            "report": report,
            "sources": sources_used[:6],
            "queries_used": queries[:3],
        }

    # ─────────────────────────────────────────────
    #  Analyze Screenshot — vision AI on browser/desktop
    # ─────────────────────────────────────────────

    def _analyze_screenshot(self, target: str = "browser", question: str = "") -> Dict:
        """Take a screenshot and analyze it with vision AI.
        
        Uses VisionAnalyzer (Ollama llava → Gemini → OpenRouter) to actually
        SEE what's on screen — essential for Instagram reels, videos, images.
        """
        # Take screenshot
        try:
            if target == "browser":
                r = self._browser.screenshot()
            else:
                r = self._desktop.screenshot()

            if not r.success or not r.screenshot_path:
                return {"success": False, "error": "Screenshot failed"}

            screenshot_path = r.screenshot_path
        except Exception as e:
            return {"success": False, "error": f"Screenshot error: {str(e)[:200]}"}

        # Analyze with vision
        if self._vision:
            try:
                technical_markers = (
                    "Look for specific technical markers: wires, circuit boards, "
                    "ESC (Electronic Speed Controllers), brushless motors, flight controllers, "
                    "carbon fiber, propellers, nozzles, lenses, sensors, or soldering joints. "
                    "Analyze the complexity: is it a simple wood structure or an electronic assembly?"
                )
                prompt = f"{question or 'Describe everything you see in this screenshot in detail.'}\n\nTECHNICAL ANALYSIS: {technical_markers}"
                
                result = self._vision.analyze_image(
                    screenshot_path, question=prompt, auto_harvest=False,
                )
                if result.success and result.description:
                    return {
                        "success": True,
                        "description": result.description[:4000],
                        "topics_detected": result.topics_detected[:10],
                        "provider": result.provider,
                        "path": screenshot_path,
                    }
            except Exception:
                pass

        # Fallback: if no vision available, try to read page text instead
        if target == "browser":
            try:
                pr = self._browser.read_page()
                if pr.success and pr.data:
                    return {
                        "success": True,
                        "description": f"[No vision model — text fallback]\n{pr.data[:4000]}",
                        "topics_detected": [],
                        "provider": "text_fallback",
                        "path": screenshot_path,
                    }
            except Exception:
                pass

        return {
            "success": True,
            "description": "[Screenshot saved but no vision model available. Install: ollama pull llava]",
            "topics_detected": [],
            "provider": "none",
            "path": screenshot_path,
        }

    def _summarize_result(self, action: str, result: Dict) -> str:
        """Create a brief human-readable summary of a step result."""
        if result.get("blocked"):
            return f"BLOCKED: {result.get('error', 'Security policy')}"
        if not result.get("success", False):
            return f"Failed: {result.get('error', 'unknown')}"

        if action == "google_search":
            return f"Searched Google → {result.get('title', '')}"
        elif action == "fast_search":
            n = result.get("count", 0)
            ms = round(result.get("duration_ms", 0))
            return f"Found {n} results ({ms}ms)"
        elif action == "open_in_chrome":
            return f"Opened in Chrome → {result.get('url', '')[:80]}"
        elif action == "answer_locally":
            src = result.get("source", "local")
            answer = result.get("answer", "")
            if src == "local":
                return f"ANSWER:{answer}"
            elif src == "local+chrome":
                return f"ANSWER:{answer}\n\n(Also opened Chrome for more details)"
            else:
                return f"Opened Chrome for answer"
        elif action == "scroll":
            return f"Scrolled page"
        elif action == "highlight":
            return f"Highlighted: {result.get('found', '')}"
        elif action in ("open_browser", "goto"):
            return f"Opened {result.get('title', result.get('url', ''))}"
        elif action == "click":
            return "Clicked element"
        elif action == "fill":
            return "Filled input"
        elif action == "read_page":
            text = result.get("text", "")
            return f"Read page ({len(text)} chars): {text[:100]}..."
        elif action == "get_links":
            n = len(result.get("links", []))
            return f"Found {n} links"
        elif action == "open_app":
            return result.get("detail", "App opened")
        elif action == "run_command":
            out = result.get("output", "")
            return f"Command output: {out[:150]}"
        elif action == "wait":
            return f"Waited {result.get('waited', 0)}s"
        elif action == "analyze_page":
            analysis = result.get("analysis", "")
            return f"Page analysis: {analysis[:200]}..."
        elif action == "deep_research":
            report = result.get("report", "")
            n_sources = len(result.get("sources", []))
            return f"Research report ({n_sources} sources): {report[:200]}..."
        elif action == "analyze_screenshot":
            desc = result.get("description", "")
            provider = result.get("provider", "unknown")
            return f"Vision analysis ({provider}): {desc[:200]}..."
        else:
            return "Done"

    # ─────────────────────────────────────────────
    #  Re-Plan (Adaptive Execution)
    # ─────────────────────────────────────────────

    def replan_after_failure(self, original_plan: ExecutionPlan, failed_step: Step, 
                             page_context: str = "") -> ExecutionPlan:
        """Ask LLM to create a new plan after a step failed."""
        prompt = f"""The original plan was: {original_plan.intent}
Step that failed: {failed_step.action}({json.dumps(failed_step.params)}) — Error: {failed_step.error}
Current page context: {page_context[:500]}

Create a new plan to recover and continue. What should we do differently?"""

        resp = self._llm.generate(
            prompt=prompt,
            system=PLANNER_SYSTEM,
            max_tokens=1024,
            temperature=0.1,
        )
        return self._parse_plan(resp.content)

    # ─────────────────────────────────────────────
    #  Full Autonomous Flow (multi-round streaming)
    # ─────────────────────────────────────────────

    def run(self, message: str) -> Generator[Dict, None, None]:
        """
        The main entry point. Multi-round observe→think→act loop.
        
        If Claude tool calling is available, uses the agentic loop
        (Claude decides one tool at a time, sees results, adapts).
        Otherwise falls back to the static plan→execute flow.
        
        Yields streaming events for real-time UI updates.
        """
        start = time.time()

        if not self.needs_tools(message):
            yield {"type": "chat_mode", "content": "This is a conversation — no tools needed."}
            return

        # Try Claude agentic loop first (multi-turn tool calling)
        if self._has_claude_tools():
            had_complete = False
            for event in self.run_agentic(message):
                if event.get("type") == "complete":
                    had_complete = True
                yield event
            if had_complete:
                return
            # Claude failed (auth error, rate limit, etc.) — fall through to plan→execute
            yield {"type": "thinking", "content": "Switching to fallback planning..."}

        # Fallback: static plan→execute loop
        current_goal = message
        self._reset_cancel()
        for round_num in range(1, self.MAX_ROUNDS + 1):
            if self._cancel_event.is_set():
                yield {"type": "cancelled", "message": "Stopped by user"}
                return

            yield {"type": "thinking", "content": f"Planning approach{f' (round {round_num})' if round_num > 1 else ''}..."}

            plan = self.create_plan(current_goal)
            if not plan.needs_tools or not plan.steps:
                if round_num == 1:
                    yield {"type": "chat_mode", "content": "No tools needed for this."}
                return

            # Execute plan (with observation + self-correction)
            last_event = None
            for event in self.execute_plan(plan):
                last_event = event
                yield event

            # After execution, decide if we need another round
            if last_event and last_event.get("type") == "complete":
                done = last_event.get("steps_done", 0)
                total = last_event.get("steps_total", 0)
                failed = last_event.get("steps_failed", 0)

                # If everything succeeded or we're out of rounds, stop
                if failed == 0 or round_num >= self.MAX_ROUNDS:
                    break

                # Some steps failed → try a continuation plan with context
                current_goal = (
                    f"Continue: {message}\n"
                    f"Previous attempt completed {done}/{total} steps. "
                    f"{failed} steps failed.\n"
                    f"Current page: {self._last_page_url}\n"
                    f"Page content: {self._last_page_text[:300]}\n"
                    f"Try a different approach for the parts that failed."
                )
                yield {"type": "observe", "content": f"Some steps failed. Adapting approach (round {round_num + 1})..."}

        # After task completes, generate proactive suggestions
        yield from self._generate_suggestions(message)

    def _generate_suggestions(self, message: str) -> Generator[Dict, None, None]:
        """Generate proactive follow-up suggestions based on what the user just asked.
        
        Uses keyword analysis + memory to suggest related actions.
        Fast and free — no LLM call needed.
        """
        msg_lower = message.lower()
        suggestions = []

        # Topic-based suggestions
        topic_suggestions = {
            "robot": [
                "Search latest robotics projects on GitHub",
                "Research Arduino vs Raspberry Pi for robotics",
                "Find robotics component prices on Amazon",
            ],
            "instagram": [
                "Search trending Instagram reels",
                "Research Instagram algorithm tips",
                "Find similar content creators",
            ],
            "youtube": [
                "Search trending videos on this topic",
                "Find related channels to subscribe",
                "Research the topic further on Wikipedia",
            ],
            "price": [
                "Compare prices across different stores",
                "Search for discount codes",
                "Find alternative cheaper options",
            ],
            "code": [
                "Search for tutorials on this",
                "Find open source examples on GitHub",
                "Research best practices",
            ],
            "movie": [
                "Find reviews for this movie",
                "Search for similar movies",
                "Find where to stream it free",
            ],
            "news": [
                "Get the latest updates on this topic",
                "Search related news articles",
                "Find expert opinions on this",
            ],
            "learn": [
                "Find free courses on this topic",
                "Search for beginner tutorials",
                "Research roadmap for this skill",
            ],
        }

        for keyword, sugs in topic_suggestions.items():
            if keyword in msg_lower:
                suggestions.extend(sugs)

        # Always add a general deep-research suggestion
        short_topic = message[:60].strip()
        suggestions.append(f"Research more about: {short_topic}")
        suggestions.append("What else can you help me with?")

        # Deduplicate and limit
        seen = set()
        unique = []
        for s in suggestions:
            if s.lower() not in seen:
                seen.add(s.lower())
                unique.append(s)
        suggestions = unique[:5]

        if suggestions:
            yield {"type": "suggestions", "items": suggestions}

    @property
    def stats(self) -> Dict:
        return {
            "total_executions": len(self._execution_history),
            "history": self._execution_history[-10:],
            "session_actions": len(self._session_context),
        }
