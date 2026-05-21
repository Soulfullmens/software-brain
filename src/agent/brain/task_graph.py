"""
task_graph.py

Hierarchical Task Execution with State Machine.
Phase R.4: The 'Will' of the Agent.

Decomposes complex goals into subgoal trees with dependencies.
"Book a flight to Dubai" → [Search flights, Compare prices, Select, Fill details, Pay (ASK USER), Confirm]

Each subgoal has a lifecycle: PENDING → ACTIVE → DONE/FAILED/BLOCKED
"""
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime


class SubGoalStatus(Enum):
    PENDING = "pending"       # Not started, waiting for dependencies
    ACTIVE = "active"         # Currently being executed
    DONE = "done"             # Successfully completed
    FAILED = "failed"         # Failed (may retry)
    BLOCKED = "blocked"       # Waiting for human input
    SKIPPED = "skipped"       # Deliberately skipped


@dataclass
class SubGoal:
    """A single step in a task execution plan."""
    id: str                              # Unique ID (e.g., "search_flights")
    name: str                            # Human-readable name
    description: str                     # What this subgoal does
    status: SubGoalStatus = SubGoalStatus.PENDING
    
    # Execution
    tool: str = ""                       # Which tool to use
    command: str = ""                    # Which command
    parameters: Dict[str, Any] = field(default_factory=dict)
    
    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # IDs of subgoals that must complete first
    
    # Safety
    requires_approval: bool = False      # Must ask human
    approval_message: str = ""           # What to ask
    
    # Result
    result: Any = None
    error: str = ""
    retry_count: int = 0
    max_retries: int = 2
    
    # Strategy
    alternative_strategies: List[Dict] = field(default_factory=list)  # Fallback approaches
    
    # Timestamps
    started_at: str = ""
    completed_at: str = ""


@dataclass
class TaskGraph:
    """
    Hierarchical goal decomposition with dependency tracking.
    
    Features:
    - Goal → ordered subgoals with dependencies
    - State machine transitions
    - Human approval gates
    - Retry with alternatives
    """
    goal: str = ""
    subgoals: List[SubGoal] = field(default_factory=list)
    current_index: int = 0
    status: str = "pending"  # pending, active, completed, failed, blocked
    
    def add_subgoal(self, sg: SubGoal):
        self.subgoals.append(sg)
    
    def get_next_subgoal(self) -> Optional[SubGoal]:
        """Get the next actionable subgoal (respecting dependencies)."""
        for sg in self.subgoals:
            if sg.status == SubGoalStatus.PENDING:
                # Check dependencies
                deps_met = all(
                    self._get_subgoal(dep_id) and 
                    self._get_subgoal(dep_id).status == SubGoalStatus.DONE
                    for dep_id in sg.depends_on
                )
                if deps_met:
                    return sg
        return None
    
    def _get_subgoal(self, sg_id: str) -> Optional[SubGoal]:
        for sg in self.subgoals:
            if sg.id == sg_id:
                return sg
        return None
    
    def activate(self, sg_id: str):
        sg = self._get_subgoal(sg_id)
        if sg:
            sg.status = SubGoalStatus.ACTIVE
            sg.started_at = datetime.now().strftime("%H:%M:%S")
            self.status = "active"
    
    def complete(self, sg_id: str, result: Any = None):
        sg = self._get_subgoal(sg_id)
        if sg:
            sg.status = SubGoalStatus.DONE
            sg.result = result
            sg.completed_at = datetime.now().strftime("%H:%M:%S")
            # Check if all done
            if all(s.status in (SubGoalStatus.DONE, SubGoalStatus.SKIPPED) 
                   for s in self.subgoals):
                self.status = "completed"
    
    def fail(self, sg_id: str, error: str):
        sg = self._get_subgoal(sg_id)
        if sg:
            sg.retry_count += 1
            if sg.retry_count <= sg.max_retries:
                sg.status = SubGoalStatus.PENDING  # Will retry
                sg.error = error
            else:
                sg.status = SubGoalStatus.FAILED
                sg.error = error
                self.status = "failed"
    
    def block(self, sg_id: str, message: str):
        sg = self._get_subgoal(sg_id)
        if sg:
            sg.status = SubGoalStatus.BLOCKED
            sg.approval_message = message
            self.status = "blocked"
    
    def approve(self, sg_id: str):
        """Human approved a blocked subgoal."""
        sg = self._get_subgoal(sg_id)
        if sg and sg.status == SubGoalStatus.BLOCKED:
            sg.status = SubGoalStatus.PENDING  # Ready to execute
            self.status = "active"
    
    def progress_summary(self) -> str:
        """Human-readable progress report."""
        done = sum(1 for s in self.subgoals if s.status == SubGoalStatus.DONE)
        total = len(self.subgoals)
        active = [s.name for s in self.subgoals if s.status == SubGoalStatus.ACTIVE]
        blocked = [s.name for s in self.subgoals if s.status == SubGoalStatus.BLOCKED]
        failed = [s.name for s in self.subgoals if s.status == SubGoalStatus.FAILED]
        
        lines = [f"Progress: {done}/{total} subgoals complete"]
        if active:
            lines.append(f"Active: {', '.join(active)}")
        if blocked:
            lines.append(f"⚠ Blocked (needs approval): {', '.join(blocked)}")
        if failed:
            lines.append(f"✗ Failed: {', '.join(failed)}")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# TASK TEMPLATES — Built-in decompositions
# ──────────────────────────────────────────────

class TaskTemplates:
    """
    Pre-built task decompositions for common operations.
    These provide instant intelligence without LLM.
    """
    
    @staticmethod
    def search_and_recommend(query: str) -> TaskGraph:
        """Search → Extract → Summarize → Recommend"""
        graph = TaskGraph(goal=f"Search and recommend: {query}")
        graph.add_subgoal(SubGoal(
            id="search", name="Search Google",
            description=f"Search for: {query}",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/search?q={query.replace(' ', '+')}"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_results", name="Scan Results",
            description="Perceive search results page",
            tool="browser_control", command="scan_page",
            parameters={},
            depends_on=["search"]
        ))
        graph.add_subgoal(SubGoal(
            id="extract_data", name="Extract Results Data",
            description="Get structured page model with links and text",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["scan_results"]
        ))
        return graph
    
    @staticmethod
    def youtube_search(query: str) -> TaskGraph:
        """Search YouTube → List videos → Recommend"""
        graph = TaskGraph(goal=f"YouTube search: {query}")
        graph.add_subgoal(SubGoal(
            id="open_youtube", name="Open YouTube Search",
            description=f"Search YouTube for: {query}",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_videos", name="Scan Video Results",
            description="Perceive video list",
            tool="browser_control", command="scan_page",
            parameters={},
            depends_on=["open_youtube"]
        ))
        graph.add_subgoal(SubGoal(
            id="extract_videos", name="Extract Video Links",
            description="Get video titles and links",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["scan_videos"]
        ))
        return graph
    
    @staticmethod
    def book_flight(destination: str, date: str = "") -> TaskGraph:
        """Full flight booking workflow (with safety gates)"""
        graph = TaskGraph(goal=f"Book flight to {destination}")
        graph.add_subgoal(SubGoal(
            id="search_flights", name="Search Flights",
            description=f"Search for flights to {destination}",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/travel/flights?q=flights+to+{destination.replace(' ', '+')}"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_options", name="Scan Flight Options",
            description="Scan available flights",
            tool="browser_control", command="scan_page",
            parameters={},
            depends_on=["search_flights"]
        ))
        graph.add_subgoal(SubGoal(
            id="extract_prices", name="Extract Prices",
            description="Get flight prices and details",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["scan_options"]
        ))
        graph.add_subgoal(SubGoal(
            id="user_selection", name="Present Options to User",
            description="Show user the best options and ask for selection",
            requires_approval=True,
            approval_message=f"Here are the flight options to {destination}. Which would you like to book?",
            depends_on=["extract_prices"]
        ))
        graph.add_subgoal(SubGoal(
            id="fill_details", name="Fill Passenger Details",
            description="Enter passenger information",
            requires_approval=True,
            approval_message="Please provide passenger details (name, passport, etc.)",
            depends_on=["user_selection"]
        ))
        graph.add_subgoal(SubGoal(
            id="payment", name="Process Payment",
            description="Complete payment",
            requires_approval=True,
            approval_message="⚠ PAYMENT REQUIRED. Please confirm to proceed with payment.",
            depends_on=["fill_details"]
        ))
        graph.add_subgoal(SubGoal(
            id="confirm", name="Save Confirmation",
            description="Screenshot and save booking confirmation",
            tool="browser_control", command="screenshot",
            parameters={"filename": "flight_booking_confirmation.png"},
            depends_on=["payment"]
        ))
        return graph
    
    @staticmethod
    def fill_form(url: str, form_data: Dict[str, str] = None) -> TaskGraph:
        """Navigate → Scan form → Fill fields → Submit (with approval)"""
        graph = TaskGraph(goal=f"Fill form at {url}")
        graph.add_subgoal(SubGoal(
            id="navigate", name="Open Form Page",
            description=f"Navigate to {url}",
            tool="browser_control", command="open_url",
            parameters={"url": url}
        ))
        graph.add_subgoal(SubGoal(
            id="scan_form", name="Scan Form",
            description="Scan page to find form fields",
            tool="browser_control", command="scan_page",
            parameters={},
            depends_on=["navigate"]
        ))
        graph.add_subgoal(SubGoal(
            id="submit_approval", name="Confirm Submission",
            description="Ask user to confirm form submission",
            requires_approval=True,
            approval_message="Form scanned. Ready to fill and submit. Proceed?",
            depends_on=["scan_form"]
        ))
        return graph
    
    @staticmethod
    def research_topic(topic: str) -> TaskGraph:
        """Multi-source research: Google + YouTube + Extract"""
        graph = TaskGraph(goal=f"Research: {topic}")
        
        # Google search
        graph.add_subgoal(SubGoal(
            id="google_search", name="Google Search",
            description=f"Search Google for {topic}",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/search?q={topic.replace(' ', '+')}"}
        ))
        graph.add_subgoal(SubGoal(
            id="google_scan", name="Scan Google Results",
            description="Extract search result data",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["google_search"]
        ))
        
        # YouTube
        graph.add_subgoal(SubGoal(
            id="youtube_search", name="YouTube Search",
            description=f"Search YouTube for {topic}",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.youtube.com/results?search_query={topic.replace(' ', '+')}"},
            depends_on=["google_scan"]
        ))
        graph.add_subgoal(SubGoal(
            id="youtube_scan", name="Scan YouTube Results",
            description="Extract video recommendations",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["youtube_search"]
        ))
        
        return graph
    
    @staticmethod
    def compare_products(product: str) -> TaskGraph:
        """Search → Visit multiple results → Compare"""
        graph = TaskGraph(goal=f"Compare: {product}")
        graph.add_subgoal(SubGoal(
            id="search", name="Search Products",
            description=f"Search for {product} comparison",
            tool="browser_control", command="open_url",
            parameters={"url": f"https://www.google.com/search?q=best+{product.replace(' ', '+')}+comparison"}
        ))
        graph.add_subgoal(SubGoal(
            id="scan", name="Scan Results",
            description="Get comparison data",
            tool="browser_control", command="get_page_model",
            parameters={},
            depends_on=["search"]
        ))
        return graph
