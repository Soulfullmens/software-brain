"""
intelligence.py

The Intelligence Layer — Phase R.4.
Smart task decomposition, search intelligence, and recommendation engine.

This is what makes the agent THINK before acting.
Instead of blindly executing, it:
1. Analyzes what the user actually wants
2. Decomposes into the right subgoals
3. Chooses the best strategy
4. Provides recommendations and insights
"""
import re
from typing import Dict, Any, Optional, List, Tuple
from .task_graph import TaskGraph, TaskTemplates, SubGoal


class TaskDecomposer:
    """
    Decomposes natural language goals into structured TaskGraphs.
    This is the agent's 'thinking' before acting.
    
    Handles:
    - Direct navigation ("go to example.com")
    - Search ("search for AI tools")
    - Research ("I want to learn about quantum computing")
    - Booking ("book a flight to Dubai")
    - Shopping ("find cheapest laptop under $500")
    - YouTube ("watch videos about Python")
    - Form filling ("fill out the application at xyz.com")
    - Comparison ("compare iPhone vs Samsung")
    - Download ("download XYZ app")
    - General help ("I want to make something today")
    """
    
    # Intent patterns — ordered by specificity
    INTENT_PATTERNS = [
        # Booking
        (r"book\s+(a\s+)?flight\s+to\s+(.+)", "book_flight"),
        (r"book\s+(a\s+)?(hotel|room)\s+(?:in|at)\s+(.+)", "book_hotel"),
        (r"book\s+(.+)", "book_general"),
        
        # Shopping / Comparison
        (r"(?:find|search|look for)\s+(?:the\s+)?cheapest\s+(.+)", "compare_products"),
        (r"compare\s+(.+)\s+(?:vs|versus|and)\s+(.+)", "compare_products"),
        (r"(?:buy|purchase|order)\s+(.+)", "shopping"),
        
        # YouTube
        (r"(?:watch|find)\s+(?:a\s+)?(?:video|videos|youtube|tutorial)s?\s+(?:about|on|for)\s+(.+)", "youtube_search"),
        (r"(?:search|find)\s+(?:on\s+)?youtube\s+(?:for\s+)?(.+)", "youtube_search"),
        (r"youtube\s+(.+)", "youtube_search"),
        
        # Download
        (r"download\s+(.+?)(?:\s+app)?$", "download"),
        (r"install\s+(.+)", "download"),
        
        # Form filling
        (r"fill\s+(?:out|in)\s+(?:the\s+)?(?:form|application)\s+(?:at|on)\s+(.+)", "fill_form"),
        
        # Research
        (r"(?:research|learn about|study|explore|understand)\s+(.+)", "research"),
        (r"(?:I\s+want\s+to\s+(?:make|build|create|learn))\s+(.+)", "research"),
        (r"(?:how\s+to|how\s+do\s+I|what\s+is|tell\s+me\s+about)\s+(.+)", "research"),
        (r"(?:today\s+I\s+want\s+to)\s+(.+)", "research"),
        
        # Search
        (r"(?:search|google|look up|find)\s+(?:for\s+)?(.+)", "search"),
        (r"(?:search|find)\s+(?:on\s+)?google\s+(?:for\s+)?(.+)", "search"),
        
        # Navigation
        (r"(?:go to|visit|open|navigate to|browse)\s+(.+)", "navigate"),
        
        # Email
        (r"(?:check|read|fetch|get)\s+(?:my\s+)?email", "check_email"),
        (r"(?:send|compose|write)\s+(?:an?\s+)?email\s+(?:to\s+)?(.+)", "send_email"),
    ]
    
    def decompose(self, goal: str) -> TaskGraph:
        """
        Analyze a natural language goal and decompose into a TaskGraph.
        
        Returns a structured plan with subgoals, dependencies, and safety gates.
        """
        goal_clean = goal.strip()
        goal_lower = goal_clean.lower()
        
        # Try each pattern
        for pattern, intent in self.INTENT_PATTERNS:
            match = re.search(pattern, goal_lower)
            if match:
                return self._build_graph(intent, goal_clean, match)
        
        # Fallback: treat as general search/research
        return self._build_graph("research", goal_clean, None)
    
    def _build_graph(self, intent: str, goal: str, match) -> TaskGraph:
        """Build a TaskGraph for a detected intent."""
        
        if intent == "book_flight":
            destination = match.group(2) if match else goal
            return TaskTemplates.book_flight(destination)
        
        if intent == "youtube_search":
            query = match.group(1) if match else goal
            return TaskTemplates.youtube_search(query)
        
        if intent == "research":
            topic = match.group(1) if match else goal
            return TaskTemplates.research_topic(topic)
        
        if intent == "compare_products":
            product = match.group(1) if match else goal
            return TaskTemplates.compare_products(product)
        
        if intent == "search":
            query = match.group(1) if match else goal
            return TaskTemplates.search_and_recommend(query)
        
        if intent == "navigate":
            target = match.group(1) if match else goal
            return self._navigate_graph(target)
        
        if intent == "fill_form":
            url = match.group(1) if match else ""
            return TaskTemplates.fill_form(url)
        
        if intent == "download":
            app_name = match.group(1) if match else goal
            return self._download_graph(app_name)
        
        if intent == "check_email":
            return self._email_check_graph(goal)
        
        if intent == "send_email":
            recipient = match.group(1) if match else ""
            return self._email_send_graph(recipient, goal)
        
        if intent == "shopping":
            item = match.group(1) if match else goal
            return self._shopping_graph(item)
        
        if intent in ("book_hotel", "book_general"):
            target = match.group(match.lastindex) if match else goal
            return self._booking_general_graph(target, intent)
        
        # Ultimate fallback
        return TaskTemplates.search_and_recommend(goal)
    
    def _navigate_graph(self, target: str) -> TaskGraph:
        """Build navigation graph."""
        # Check if it's a URL
        url = target
        if not url.startswith("http"):
            if "." in url and " " not in url:
                url = "https://" + url
            else:
                # Not a URL — search for it
                return TaskTemplates.search_and_recommend(target)
        
        graph = TaskGraph(goal=f"Navigate to {target}")
        graph.add_subgoal(SubGoal(
            id="open_page", name="Open Page",
            description=f"Navigate to {url}",
            tool="browser_control", command="open_url",
            parameters={"url": url}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_page", name="Perceive Page",
            description="Scan page content and structure",
            tool="browser_control", command="scan_page",
            parameters={},
            depends_on=["open_page"]
        ))
        return graph
    
    def _download_graph(self, app_name: str) -> TaskGraph:
        """Build download/install graph."""
        graph = TaskGraph(goal=f"Download {app_name}")
        graph.add_subgoal(SubGoal(
            id="search_download", name="Search for Download",
            description=f"Search for official {app_name} download",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/search?q=download+{app_name.replace(' ', '+')}+official"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_results", name="Scan Results",
            description="Find official download links",
            tool="browser_control", command="scan_page",
            parameters={},
            depends_on=["search_download"]
        ))
        graph.add_subgoal(SubGoal(
            id="extract_links", name="Extract Download Links",
            description="Get download page URLs",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["scan_results"]
        ))
        graph.add_subgoal(SubGoal(
            id="user_confirm", name="Confirm Download",
            description="Ask user to confirm download source",
            requires_approval=True,
            approval_message=f"Found download options for {app_name}. Which one should I proceed with?",
            depends_on=["extract_links"]
        ))
        return graph
    
    def _email_check_graph(self, goal: str) -> TaskGraph:
        """Build email check graph."""
        subject = ""
        if "for" in goal.lower():
            subject = goal.lower().split("for", 1)[1].strip()
        
        graph = TaskGraph(goal=f"Check email")
        graph.add_subgoal(SubGoal(
            id="fetch_email", name="Fetch Emails",
            description=f"Fetch emails{' about ' + subject if subject else ''}",
            tool="email_communication", command="fetch_and_download",
            parameters={"subject_filter": subject, "save_dir": "./downloads"}
        ))
        return graph
    
    def _email_send_graph(self, recipient: str, goal: str) -> TaskGraph:
        """Build email send graph."""
        graph = TaskGraph(goal=f"Send email to {recipient}")
        graph.add_subgoal(SubGoal(
            id="compose_approval", name="Review Email",
            description="Ask user to review email before sending",
            requires_approval=True,
            approval_message=f"Ready to compose email to {recipient}. Please provide subject and body.",
        ))
        return graph
    
    def _shopping_graph(self, item: str) -> TaskGraph:
        """Build shopping graph with safety gates."""
        graph = TaskGraph(goal=f"Shop for {item}")
        graph.add_subgoal(SubGoal(
            id="search_prices", name="Search Prices",
            description=f"Search for {item} prices",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/search?q=buy+{item.replace(' ', '+')}+best+price"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_options", name="Scan Options",
            description="Compare available options",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["search_prices"]
        ))
        graph.add_subgoal(SubGoal(
            id="user_selection", name="User Selection",
            description="Present options to user",
            requires_approval=True,
            approval_message=f"Here are the options for {item}. Which would you like to buy?",
            depends_on=["scan_options"]
        ))
        graph.add_subgoal(SubGoal(
            id="purchase", name="Complete Purchase",
            description="Process purchase",
            requires_approval=True,
            approval_message=f"⚠️ PURCHASE: Ready to buy {item}. Confirm payment?",
            depends_on=["user_selection"]
        ))
        return graph
    
    def _booking_general_graph(self, target: str, intent: str) -> TaskGraph:
        """Build generic booking graph."""
        graph = TaskGraph(goal=f"Book {target}")
        graph.add_subgoal(SubGoal(
            id="search", name="Search Options",
            description=f"Search for {target}",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/search?q=book+{target.replace(' ', '+')}"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan", name="Scan Results",
            description="Review available options",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["search"]
        ))
        graph.add_subgoal(SubGoal(
            id="select", name="User Selection",
            description="Present options and get user choice",
            requires_approval=True,
            approval_message=f"Found booking options for {target}. Which one?",
            depends_on=["scan"]
        ))
        graph.add_subgoal(SubGoal(
            id="payment", name="Payment",
            description="Process booking payment",
            requires_approval=True,
            approval_message=f"⚠️ PAYMENT: Confirm booking payment for {target}?",
            depends_on=["select"]
        ))
        return graph


class SearchIntelligence:
    """
    Smart search result extraction and recommendation.
    
    After scanning a search results page, this module:
    1. Extracts relevant links/titles
    2. Categorizes results
    3. Provides recommendations
    """
    
    @staticmethod
    def extract_recommendations(page_model: Dict) -> Dict[str, Any]:
        """
        Extract organized recommendations from a page model.
        
        Returns:
        {
            "top_results": [{"title": ..., "url": ..., "snippet": ...}],
            "video_results": [...],
            "related_searches": [...],
            "recommendation": "Based on results, ..."
        }
        """
        elements = page_model.get("elements", [])
        
        top_results = []
        video_results = []
        
        for elem in elements:
            if isinstance(elem, dict):
                tag = elem.get("tag", "")
                text = elem.get("text", "")[:150]
                href = elem.get("href", "")
                
                if tag == "a" and href and text and len(text) > 10:
                    entry = {"title": text, "url": href}
                    
                    # Categorize
                    if "youtube.com" in href or "youtu.be" in href:
                        video_results.append(entry)
                    elif href.startswith("http") and "google.com" not in href:
                        if len(top_results) < 10:
                            top_results.append(entry)
        
        recommendation = ""
        if video_results:
            recommendation += f"📺 Found {len(video_results)} video(s) that might help. "
        if top_results:
            recommendation += f"🔗 Found {len(top_results)} relevant web result(s)."
        
        return {
            "top_results": top_results,
            "video_results": video_results,
            "total_results": len(top_results) + len(video_results),
            "recommendation": recommendation
        }
    
    @staticmethod
    def format_results_for_user(recommendations: Dict) -> str:
        """Format recommendations as human-readable text."""
        lines = ["📋 Search Results:\n"]
        
        if recommendations.get("top_results"):
            lines.append("🔗 **Web Results:**")
            for i, r in enumerate(recommendations["top_results"][:5], 1):
                lines.append(f"  {i}. {r['title']}")
                lines.append(f"     {r['url']}")
            lines.append("")
        
        if recommendations.get("video_results"):
            lines.append("📺 **Video Results:**")
            for i, r in enumerate(recommendations["video_results"][:3], 1):
                lines.append(f"  {i}. {r['title']}")
                lines.append(f"     {r['url']}")
            lines.append("")
        
        if recommendations.get("recommendation"):
            lines.append(f"💡 {recommendations['recommendation']}")
        
        return "\n".join(lines)
