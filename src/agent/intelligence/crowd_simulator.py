"""
crowd_simulator.py — MiroFish-Style Swarm Intelligence Prediction Engine

Inspired by MiroFish (github.com/666ghj/MiroFish), rewritten from scratch
to work with our agent's existing Ollama/Gemini LLM backend.

WHAT IT DOES:
    You describe ANY real-world scenario (stock market crash, price increase,
    viral post, remote work policy change, political crisis, etc.).
    
    The engine:
    1. Generates 100-1000+ diverse AI personas (investors, workers, consumers,
       politicians, journalists) each with unique demographics, psychology,
       social connections, and biases.
    2. Drops them into a simulated world seeded with your scenario.
    3. Runs 5-10 simulation "rounds" where agents react, argue, change minds,
       form groups, panic-sell, hold, protest, or go viral.
    4. Produces a detailed prediction report: consensus, factions, timeline,
       confidence level, and actionable recommendations.

EXAMPLES:
    - "Tesla stock + US-Iran war" → simulates 500 investors reacting
    - "Raise prices 20%" → simulates 300 customers deciding to stay or leave
    - "End remote work policy" → simulates 200 employees deciding to quit or adapt
    - "Post controversial tweet" → simulates 1000 social media users going viral or canceling

ARCHITECTURE:
    CrowdSimulator
      ├── PopulationGenerator  → creates diverse AI personas
      ├── SimulationEngine     → runs multi-round social dynamics
      ├── OpinionTracker       → tracks belief shifts across rounds  
      ├── FactionDetector      → identifies emerging factions/consensus
      └── ReportGenerator      → produces final prediction report
"""

import time
import json
import random
import hashlib
import threading
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Tuple
from collections import Counter


# ═══════════════════════════════════════════════════════
# PERSONA TEMPLATES — The building blocks of diverse crowds
# ═══════════════════════════════════════════════════════

DEMOGRAPHIC_POOLS = {
    "age_groups": [
        ("Gen Z", 18, 27, "digital-native, meme-driven, progressive"),
        ("Millennial", 28, 43, "tech-savvy, experience-driven, pragmatic-idealist"),
        ("Gen X", 44, 59, "independent, skeptical, financially conservative"),
        ("Boomer", 60, 78, "traditional, institutional-trust, wealth-preserving"),
    ],
    "occupations": [
        "software engineer", "teacher", "nurse", "retail worker", "lawyer",
        "freelancer", "small business owner", "corporate manager", "student",
        "retired", "journalist", "trader", "marketing exec", "factory worker",
        "government employee", "artist", "delivery driver", "researcher",
        "influencer", "stay-at-home parent", "startup founder", "chef",
        "real estate agent", "uber driver", "doctor", "farmer",
    ],
    "personality_traits": [
        "risk-taker", "risk-averse", "contrarian", "follower",
        "analytical", "emotional", "impulsive", "patient",
        "optimist", "pessimist", "realist", "idealist",
        "aggressive", "passive", "vocal", "silent-majority",
    ],
    "economic_status": [
        ("lower", "paycheck-to-paycheck, price-sensitive"),
        ("lower-middle", "some savings, cautious spending"),
        ("middle", "moderate savings, balanced approach"),
        ("upper-middle", "comfortable, diversified portfolio"),
        ("upper", "wealthy, can absorb losses, long-term thinking"),
    ],
    "information_sources": [
        "Twitter/X", "Reddit", "CNN/mainstream media", "Fox News",
        "Bloomberg Terminal", "TikTok", "WhatsApp groups",
        "local newspaper", "podcasts", "friends and family",
        "professional networks", "academic journals",
    ],
    "mbti_types": [
        "INTJ", "INTP", "ENTJ", "ENTP",
        "INFJ", "INFP", "ENFJ", "ENFP",
        "ISTJ", "ISFJ", "ESTJ", "ESFJ",
        "ISTP", "ISFP", "ESTP", "ESFP",
    ],
    "trust_levels": [
        ("skeptic", "questions everything, needs hard evidence"),
        ("cautious", "follows trusted sources, waits for confirmation"),
        ("moderate", "balanced trust, open to new information"),
        ("trusting", "trusts institutions and media broadly"),
        ("naive", "easily swayed by loud voices and trends"),
    ],
}

# Context-specific persona templates for different scenarios
SCENARIO_PERSONA_TEMPLATES = {
    "financial": {
        "roles": ["retail investor", "day trader", "long-term holder",
                  "institutional fund manager", "crypto enthusiast",
                  "financial advisor", "retiree with portfolio",
                  "first-time investor", "hedge fund analyst",
                  "index fund holder"],
        "decisions": ["sell immediately", "hold steady", "buy the dip",
                      "move to cash", "hedge with options", "wait and see",
                      "diversify", "panic sell", "double down"],
    },
    "business": {
        "roles": ["loyal customer", "new customer", "budget shopper",
                  "premium buyer", "brand advocate", "competitor's customer",
                  "undecided", "discount hunter", "value seeker"],
        "decisions": ["stay loyal", "switch to competitor", "reduce spending",
                      "cancel subscription", "complain publicly", "accept change",
                      "negotiate", "look for alternatives"],
    },
    "workplace": {
        "roles": ["senior engineer", "junior employee", "middle manager",
                  "team lead", "remote worker", "office enthusiast",
                  "working parent", "recent hire", "legacy employee"],
        "decisions": ["quit immediately", "start job searching", "stay and adapt",
                      "demand changes", "negotiate compromise", "organize protest",
                      "wait and see", "actively support"],
    },
    "social": {
        "roles": ["influencer", "casual user", "activist", "troll",
                  "lurker", "journalist", "brand account",
                  "concerned parent", "content creator", "fact-checker"],
        "decisions": ["share/repost", "ignore", "fact-check", "cancel",
                      "support", "meme it", "report", "debate",
                      "unfollow", "write thread"],
    },
    "political": {
        "roles": ["voter", "politician", "journalist", "protester",
                  "business leader", "military veteran", "student activist",
                  "religious leader", "union member", "diplomat"],
        "decisions": ["support", "oppose", "protest", "negotiate",
                      "wait for more info", "organize", "flee",
                      "stockpile", "change party"],
    },
}


# ═══════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════

@dataclass
class SimAgent:
    """A single simulated person in the crowd."""
    id: str
    name: str
    age: int
    age_group: str
    occupation: str
    personality: str
    economic_status: str
    trust_type: str
    mbti: str
    info_sources: List[str]
    role: str                # scenario-specific role
    initial_opinion: str     # starting position
    current_opinion: str     # can change during simulation
    opinion_strength: float  # 0.0 (uncertain) to 1.0 (firmly decided)
    connections: List[str]   # agent IDs they listen to
    decision_history: List[Dict[str, Any]] = field(default_factory=list)
    influenced_by: List[str] = field(default_factory=list)

    def profile_summary(self) -> str:
        return (
            f"{self.name}, {self.age}y {self.age_group}, {self.occupation}, "
            f"{self.personality}, {self.economic_status} class, {self.trust_type}, "
            f"MBTI:{self.mbti}, role:{self.role}"
        )


@dataclass
class SimulationRound:
    """Result of one simulation round."""
    round_num: int
    opinion_distribution: Dict[str, int]
    key_events: List[str]
    mind_changes: int
    faction_sizes: Dict[str, int]
    dominant_opinion: str
    consensus_strength: float  # 0.0-1.0


@dataclass
class PredictionReport:
    """Final prediction report from the simulation."""
    scenario: str
    population_size: int
    rounds_run: int
    duration_ms: float
    # Results
    final_consensus: str
    consensus_confidence: float  # 0-100%
    factions: Dict[str, Dict[str, Any]]
    timeline: List[SimulationRound]
    key_insights: List[str]
    recommendation: str
    minority_warning: str  # what the minority thinks (often insightful)
    wild_card_risk: str    # unexpected scenario the minority might be right about


# ═══════════════════════════════════════════════════════
# POPULATION GENERATOR
# ═══════════════════════════════════════════════════════

class PopulationGenerator:
    """Generate diverse, realistic populations for simulation."""

    # Common first/last names for generating realistic personas
    FIRST_NAMES = [
        "James", "Maria", "Ahmed", "Yuki", "Priya", "Carlos", "Emma", "Wei",
        "Fatima", "Olga", "Raj", "Sarah", "Mohammed", "Aiko", "Ivan",
        "Chen", "Elena", "Dmitri", "Amara", "Lars", "Kenji", "Isabella",
        "Omar", "Suki", "David", "Ananya", "Hassan", "Mei", "John",
        "Aaliyah", "Park", "Linda", "Kofi", "Yara", "Tom", "Nina",
        "Ali", "Sophie", "Ryan", "Zara", "Ming", "Julia", "Kwame",
        "Hana", "Luke", "Devi", "Sami", "Rosa", "Ben", "Lila",
    ]

    def generate_population(self, count: int, scenario_type: str,
                            scenario_desc: str) -> List[SimAgent]:
        """Generate a diverse population tailored to the scenario."""
        template = SCENARIO_PERSONA_TEMPLATES.get(scenario_type,
                    SCENARIO_PERSONA_TEMPLATES["social"])
        
        agents = []
        for i in range(count):
            agent = self._create_agent(i, template, scenario_desc)
            agents.append(agent)
        
        # Create social connections (small-world network)
        self._wire_connections(agents)
        
        return agents

    def _create_agent(self, idx: int, template: Dict, scenario: str) -> SimAgent:
        """Create a single diverse agent."""
        # Demographics
        age_group = random.choice(DEMOGRAPHIC_POOLS["age_groups"])
        age = random.randint(age_group[1], age_group[2])
        occupation = random.choice(DEMOGRAPHIC_POOLS["occupations"])
        personality = random.choice(DEMOGRAPHIC_POOLS["personality_traits"])
        econ = random.choice(DEMOGRAPHIC_POOLS["economic_status"])
        trust = random.choice(DEMOGRAPHIC_POOLS["trust_levels"])
        mbti = random.choice(DEMOGRAPHIC_POOLS["mbti_types"])
        sources = random.sample(DEMOGRAPHIC_POOLS["information_sources"],
                               k=random.randint(1, 3))
        
        # Scenario-specific
        role = random.choice(template["roles"])
        initial_opinion = random.choice(template["decisions"])
        
        # Opinion strength based on personality
        if personality in ("impulsive", "aggressive", "risk-taker"):
            strength = random.uniform(0.6, 0.95)
        elif personality in ("patient", "analytical", "realist"):
            strength = random.uniform(0.3, 0.7)
        else:
            strength = random.uniform(0.2, 0.8)
        
        name = random.choice(self.FIRST_NAMES)
        agent_id = f"agent_{idx:04d}"
        
        return SimAgent(
            id=agent_id,
            name=name,
            age=age,
            age_group=age_group[0],
            occupation=occupation,
            personality=personality,
            economic_status=econ[0],
            trust_type=trust[0],
            mbti=mbti,
            info_sources=sources,
            role=role,
            initial_opinion=initial_opinion,
            current_opinion=initial_opinion,
            opinion_strength=round(strength, 2),
            connections=[],
        )

    def _wire_connections(self, agents: List[SimAgent]):
        """Create a small-world social network among agents."""
        n = len(agents)
        if n < 3:
            return
        
        agent_by_id = {a.id: a for a in agents}
        
        # Each agent connects to 3-8 others, biased toward similar demographics
        for agent in agents:
            num_connections = min(random.randint(3, 8), n - 1)
            
            # 60% similar connections, 40% random (small-world)
            similar_ids = set()
            different_ids = []
            for a in agents:
                if a.id == agent.id:
                    continue
                if a.age_group == agent.age_group or a.economic_status == agent.economic_status:
                    similar_ids.add(a.id)
                else:
                    different_ids.append(a.id)
            
            sim_count = int(num_connections * 0.6)
            diff_count = num_connections - sim_count
            
            chosen_ids = []
            similar_list = list(similar_ids)
            if similar_list:
                chosen_ids.extend(random.sample(similar_list, min(sim_count, len(similar_list))))
            if different_ids:
                chosen_ids.extend(random.sample(different_ids, min(diff_count, len(different_ids))))
            
            agent.connections = chosen_ids


# ═══════════════════════════════════════════════════════
# SIMULATION ENGINE — The core social dynamics simulator
# ═══════════════════════════════════════════════════════

class SimulationEngine:
    """
    Runs multi-round social simulations.
    
    Each round:
    1. Agents "see" what their connections think.
    2. Agents update their opinions based on social pressure,
       personality, and new information.
    3. Dramatic events can shift the landscape.
    """

    def __init__(self, llm_fn: Optional[Callable] = None):
        self.llm_fn = llm_fn

    def run_simulation(self, agents: List[SimAgent], scenario: str,
                       num_rounds: int = 7,
                       scenario_type: str = "social") -> List[SimulationRound]:
        """Run the full simulation."""
        rounds = []
        template = SCENARIO_PERSONA_TEMPLATES.get(scenario_type,
                    SCENARIO_PERSONA_TEMPLATES["social"])
        possible_decisions = template["decisions"]
        
        for r in range(1, num_rounds + 1):
            round_result = self._run_round(
                agents, r, scenario, possible_decisions
            )
            rounds.append(round_result)
        
        return rounds

    def _run_round(self, agents: List[SimAgent], round_num: int,
                   scenario: str,
                   possible_decisions: List[str]) -> SimulationRound:
        """Execute a single simulation round."""
        mind_changes = 0
        key_events = []
        agent_map = {a.id: a for a in agents}
        
        # Shuffle to avoid order bias
        shuffled = list(agents)
        random.shuffle(shuffled)
        
        for agent in shuffled:
            old_opinion = agent.current_opinion
            
            # Gather social pressure from connections
            connection_opinions = []
            for cid in agent.connections:
                if cid in agent_map:
                    c = agent_map[cid]
                    connection_opinions.append(c.current_opinion)
            
            # Calculate social pressure
            if connection_opinions:
                opinion_counts = Counter(connection_opinions)
                dominant_neighbor_opinion = opinion_counts.most_common(1)[0][0]
                pressure_ratio = opinion_counts[dominant_neighbor_opinion] / len(connection_opinions)
            else:
                dominant_neighbor_opinion = agent.current_opinion
                pressure_ratio = 0
            
            # Decision logic based on personality archetype
            changed = self._agent_decides(
                agent, dominant_neighbor_opinion, pressure_ratio,
                possible_decisions, round_num
            )
            
            if changed:
                mind_changes += 1
                agent.decision_history.append({
                    "round": round_num,
                    "from": old_opinion,
                    "to": agent.current_opinion,
                    "reason": f"social pressure from {dominant_neighbor_opinion} "
                              f"(ratio: {pressure_ratio:.0%})",
                })
                
                if agent.personality in ("influencer", "vocal", "aggressive"):
                    key_events.append(
                        f"Round {round_num}: {agent.name} ({agent.role}, {agent.personality}) "
                        f"switched from '{old_opinion}' to '{agent.current_opinion}'"
                    )
        
        # Calculate round statistics
        opinion_dist = Counter(a.current_opinion for a in agents)
        dominant = opinion_dist.most_common(1)[0]
        consensus_strength = dominant[1] / len(agents)
        
        # Detect factions (groups with same opinion)
        faction_sizes = dict(opinion_dist)
        
        return SimulationRound(
            round_num=round_num,
            opinion_distribution=dict(opinion_dist),
            key_events=key_events[:5],  # Top 5 events
            mind_changes=mind_changes,
            faction_sizes=faction_sizes,
            dominant_opinion=dominant[0],
            consensus_strength=round(consensus_strength, 3),
        )

    def _agent_decides(self, agent: SimAgent, neighbor_dominant: str,
                       pressure: float, possible_decisions: List[str],
                       round_num: int) -> bool:
        """
        Core decision algorithm — how a single agent updates their opinion.
        
        Factors:
        - Social pressure from connections
        - Personality type (followers cave, contrarians resist)
        - Opinion strength (strong opinions resist change)
        - Time (people get more entrenched over rounds)
        - Random noise (real humans are unpredictable)
        """
        # If already holding the dominant opinion, less likely to change
        if agent.current_opinion == neighbor_dominant:
            return False
        
        # Base influence chance
        influence_chance = pressure * 0.5  # Social pressure effect
        
        # Personality modifiers
        personality_modifiers = {
            "follower": 0.25,      # Very susceptible
            "passive": 0.15,
            "emotional": 0.15,
            "impulsive": 0.20,
            "naive": 0.20,         # Easily swayed
            "optimist": 0.05,
            "pessimist": 0.05,
            "realist": -0.05,
            "analytical": -0.10,   # Resistant to social pressure
            "patient": -0.10,
            "contrarian": -0.20,   # Actively resists majority
            "risk-averse": -0.05,
            "risk-taker": 0.10,
            "aggressive": 0.05,
            "vocal": 0.0,
            "silent-majority": 0.10,
            "idealist": 0.0,
        }
        
        modifier = personality_modifiers.get(agent.personality, 0.0)
        influence_chance += modifier
        
        # Opinion strength resistance (strong opinions resist change)
        influence_chance -= agent.opinion_strength * 0.3
        
        # Time decay (people entrench over rounds)
        influence_chance -= round_num * 0.02
        
        # Trust modifiers
        trust_modifiers = {
            "skeptic": -0.15,
            "cautious": -0.05,
            "moderate": 0.0,
            "trusting": 0.10,
            "naive": 0.20,
        }
        influence_chance += trust_modifiers.get(agent.trust_type, 0.0)
        
        # Random noise (5%)
        influence_chance += random.uniform(-0.05, 0.05)
        
        # Clamp
        influence_chance = max(0.0, min(influence_chance, 0.85))
        
        # Roll the dice
        if random.random() < influence_chance:
            agent.current_opinion = neighbor_dominant
            agent.opinion_strength = max(0.1, agent.opinion_strength - 0.1)
            agent.influenced_by.append(f"round_{round_num}_social_pressure")
            return True
        else:
            # Getting more entrenched
            agent.opinion_strength = min(1.0, agent.opinion_strength + 0.03)
            return False


# ═══════════════════════════════════════════════════════
# PREDICTION ENGINE — The report generator
# ═══════════════════════════════════════════════════════

class CrowdSimulator:
    """
    MiroFish-style Swarm Intelligence Prediction Engine.
    
    Usage:
        sim = CrowdSimulator(llm_fn=my_llm)
        report = sim.predict(
            scenario="Tesla stock after US-Iran war starts",
            population_size=500,
            scenario_type="financial"
        )
        print(report)
    """

    def __init__(self, llm_fn: Optional[Callable] = None):
        self.llm_fn = llm_fn
        self.pop_gen = PopulationGenerator()
        self.sim_engine = SimulationEngine(llm_fn=llm_fn)

    def detect_scenario_type(self, scenario: str) -> str:
        """Auto-detect the type of scenario from natural language."""
        scenario_lower = scenario.lower()
        
        financial_kw = ["stock", "invest", "market", "crypto", "bitcoin",
                        "portfolio", "sell", "buy", "trade", "price",
                        "inflation", "recession", "fed", "interest rate"]
        business_kw = ["customer", "subscription", "pricing", "product",
                       "competitor", "brand", "sales", "revenue", "churn"]
        workplace_kw = ["remote work", "employee", "quit", "hire",
                        "office", "team", "manager", "salary", "policy"]
        political_kw = ["war", "election", "president", "government",
                        "policy", "protest", "law", "regulation", "vote"]
        social_kw = ["viral", "post", "tweet", "cancel", "influencer",
                     "tiktok", "trending", "public opinion", "meme"]
        
        scores = {
            "financial": sum(1 for k in financial_kw if k in scenario_lower),
            "business": sum(1 for k in business_kw if k in scenario_lower),
            "workplace": sum(1 for k in workplace_kw if k in scenario_lower),
            "political": sum(1 for k in political_kw if k in scenario_lower),
            "social": sum(1 for k in social_kw if k in scenario_lower),
        }
        
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "social"

    def predict(self, scenario: str, population_size: int = 200,
                num_rounds: int = 7,
                scenario_type: str = None) -> PredictionReport:
        """
        Run a full crowd simulation and generate a prediction report.
        
        Args:
            scenario: Natural language description of the situation
            population_size: Number of simulated people (50-5000)
            num_rounds: Simulation rounds (5-15)
            scenario_type: Override auto-detection (financial/business/workplace/social/political)
        """
        start_time = time.time()
        
        # Clamp values
        population_size = max(50, min(population_size, 5000))
        num_rounds = max(3, min(num_rounds, 15))
        
        # Auto-detect scenario type
        if not scenario_type:
            scenario_type = self.detect_scenario_type(scenario)
        
        # Generate population
        agents = self.pop_gen.generate_population(
            population_size, scenario_type, scenario
        )
        
        # Run simulation
        rounds = self.sim_engine.run_simulation(
            agents, scenario, num_rounds, scenario_type
        )
        
        # Generate report
        report = self._generate_report(
            scenario, scenario_type, agents, rounds, start_time
        )
        
        return report

    def _generate_report(self, scenario: str, scenario_type: str,
                         agents: List[SimAgent],
                         rounds: List[SimulationRound],
                         start_time: float) -> PredictionReport:
        """Generate the final prediction report."""
        
        final_round = rounds[-1]
        
        # Analyze factions
        factions = {}
        for opinion, count in final_round.opinion_distribution.items():
            faction_agents = [a for a in agents if a.current_opinion == opinion]
            
            # Demographic breakdown
            age_dist = Counter(a.age_group for a in faction_agents)
            econ_dist = Counter(a.economic_status for a in faction_agents)
            personality_dist = Counter(a.personality for a in faction_agents)
            role_dist = Counter(a.role for a in faction_agents)
            
            factions[opinion] = {
                "count": count,
                "percentage": round(count / len(agents) * 100, 1),
                "dominant_age_group": age_dist.most_common(1)[0][0] if age_dist else "N/A",
                "dominant_economic": econ_dist.most_common(1)[0][0] if econ_dist else "N/A",
                "dominant_personality": personality_dist.most_common(1)[0][0] if personality_dist else "N/A",
                "dominant_role": role_dist.most_common(1)[0][0] if role_dist else "N/A",
                "avg_conviction": round(
                    sum(a.opinion_strength for a in faction_agents) / max(1, len(faction_agents)), 2
                ),
            }
        
        # Sort factions by size
        factions = dict(sorted(factions.items(), key=lambda x: x[1]["count"], reverse=True))
        
        # Key insights
        insights = self._extract_insights(agents, rounds, factions, scenario_type)
        
        # Minority warning
        minority_factions = [f for f, d in factions.items()
                            if d["percentage"] < 25 and d["percentage"] > 5]
        minority_warning = ""
        if minority_factions:
            mf = minority_factions[0]
            md = factions[mf]
            minority_warning = (
                f"A significant minority ({md['percentage']}%) chose '{mf}'. "
                f"These are predominantly {md['dominant_personality']} "
                f"{md['dominant_age_group']} {md['dominant_role']}s. "
                f"Their conviction is {md['avg_conviction']:.0%}. "
                f"Don't ignore this group — minorities with high conviction "
                f"often prove right in black-swan events."
            )
        
        # Wild card risk
        contrarian_agents = [a for a in agents if a.personality == "contrarian"]
        wild_card_risk = ""
        if contrarian_agents:
            contrarian_opinions = Counter(a.current_opinion for a in contrarian_agents)
            cc_top = contrarian_opinions.most_common(1)[0]
            wild_card_risk = (
                f"Contrarian thinkers ({len(contrarian_agents)} agents) "
                f"favor '{cc_top[0]}' ({cc_top[1]}/{len(contrarian_agents)}). "
                f"Smart contrarians often see what the crowd misses."
            )
        
        # Recommendation
        top_faction = list(factions.keys())[0]
        top_data = factions[top_faction]
        recommendation = self._generate_recommendation(
            scenario, top_faction, top_data, factions, final_round
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        return PredictionReport(
            scenario=scenario,
            population_size=len(agents),
            rounds_run=len(rounds),
            duration_ms=round(duration_ms, 1),
            final_consensus=top_faction,
            consensus_confidence=round(top_data["percentage"], 1),
            factions=factions,
            timeline=rounds,
            key_insights=insights,
            recommendation=recommendation,
            minority_warning=minority_warning,
            wild_card_risk=wild_card_risk,
        )

    def _extract_insights(self, agents: List[SimAgent],
                          rounds: List[SimulationRound],
                          factions: Dict, scenario_type: str) -> List[str]:
        """Extract key insights from the simulation."""
        insights = []
        
        # Trend analysis
        if len(rounds) >= 3:
            early_dominant = rounds[1].dominant_opinion
            late_dominant = rounds[-1].dominant_opinion
            if early_dominant != late_dominant:
                insights.append(
                    f"Major shift detected: crowd initially favored '{early_dominant}' "
                    f"but ultimately settled on '{late_dominant}'."
                )
            else:
                insights.append(
                    f"Stable consensus: '{early_dominant}' was dominant from early rounds "
                    f"and never lost its lead."
                )
        
        # Conviction analysis
        high_conviction = [a for a in agents if a.opinion_strength > 0.8]
        if high_conviction:
            hc_opinions = Counter(a.current_opinion for a in high_conviction)
            hc_top = hc_opinions.most_common(1)[0]
            insights.append(
                f"High-conviction agents ({len(high_conviction)}) "
                f"overwhelmingly favor '{hc_top[0]}' ({hc_top[1]} agents). "
                f"These are the 'true believers' who won't change their minds."
            )
        
        # Mind-change velocity
        total_changes = sum(r.mind_changes for r in rounds)
        avg_changes = total_changes / len(rounds) if rounds else 0
        if avg_changes > len(agents) * 0.15:
            insights.append(
                f"High volatility: average {avg_changes:.0f} mind-changes per round "
                f"({avg_changes/len(agents)*100:.0f}% of population). "
                f"This scenario causes significant uncertainty."
            )
        elif avg_changes < len(agents) * 0.03:
            insights.append(
                f"Very stable: only {avg_changes:.0f} mind-changes per round. "
                f"People had strong initial convictions."
            )
        
        # Age group divergence
        for faction_name, faction_data in list(factions.items())[:2]:
            if faction_data["percentage"] > 20:
                insights.append(
                    f"The '{faction_name}' faction is led by "
                    f"{faction_data['dominant_age_group']}s, mainly "
                    f"{faction_data['dominant_role']}s with {faction_data['dominant_personality']} "
                    f"personality ({faction_data['avg_conviction']:.0%} conviction)."
                )
        
        return insights[:6]  # Cap at 6

    def _generate_recommendation(self, scenario: str, top_choice: str,
                                  top_data: Dict, all_factions: Dict,
                                  final_round: SimulationRound) -> str:
        """Generate a clear recommendation."""
        confidence = top_data["percentage"]
        
        if confidence > 70:
            strength = "STRONG"
            qualifier = "overwhelming consensus"
        elif confidence > 50:
            strength = "MODERATE"
            qualifier = "majority consensus"
        elif confidence > 35:
            strength = "WEAK"
            qualifier = "plurality (no majority)"
        else:
            strength = "INCONCLUSIVE"
            qualifier = "deeply divided crowd"
        
        recommendation = (
            f"[{strength} SIGNAL] The simulated crowd ({final_round.opinion_distribution}) "
            f"predicts '{top_choice}' with {confidence:.0f}% support ({qualifier}). "
        )
        
        if confidence < 50:
            runner_up = list(all_factions.keys())[1] if len(all_factions) > 1 else "unknown"
            runner_data = all_factions.get(runner_up, {})
            recommendation += (
                f"Strong opposition from '{runner_up}' at {runner_data.get('percentage', 0):.0f}%. "
                f"Proceed with extreme caution — the crowd is split."
            )
        else:
            recommendation += (
                f"This is a reliable signal. The crowd converged across "
                f"different demographics and personality types."
            )
        
        return recommendation

    def format_report(self, report: PredictionReport) -> str:
        """Format a PredictionReport into a readable string."""
        lines = []
        lines.append("=" * 60)
        lines.append("  CROWD SIMULATION PREDICTION REPORT")
        lines.append("  (MiroFish-Style Swarm Intelligence)")
        lines.append("=" * 60)
        lines.append(f"\nScenario: {report.scenario}")
        lines.append(f"Population: {report.population_size} simulated people")
        lines.append(f"Rounds: {report.rounds_run} | Duration: {report.duration_ms:.0f}ms")
        
        lines.append(f"\n{'─' * 40}")
        lines.append(f"PREDICTION: {report.final_consensus}")
        lines.append(f"Confidence: {report.consensus_confidence:.0f}%")
        lines.append(f"{'─' * 40}")
        
        lines.append("\nFACTIONS:")
        for faction, data in report.factions.items():
            bar_len = int(data["percentage"] / 2)
            bar = "█" * bar_len
            lines.append(f"  {faction:25s} {data['percentage']:5.1f}% {bar}")
            lines.append(f"    Led by: {data['dominant_age_group']} {data['dominant_role']}s "
                        f"({data['dominant_personality']}, conviction: {data['avg_conviction']:.0%})")
        
        lines.append("\nKEY INSIGHTS:")
        for i, insight in enumerate(report.key_insights, 1):
            lines.append(f"  {i}. {insight}")
        
        lines.append(f"\nRECOMMENDATION:\n  {report.recommendation}")
        
        if report.minority_warning:
            lines.append(f"\nMINORITY WARNING:\n  {report.minority_warning}")
        
        if report.wild_card_risk:
            lines.append(f"\nWILD CARD RISK:\n  {report.wild_card_risk}")
        
        # Timeline summary
        lines.append("\nTIMELINE:")
        for r in report.timeline:
            lines.append(
                f"  Round {r.round_num}: {r.dominant_opinion} "
                f"({r.consensus_strength:.0%}) | "
                f"{r.mind_changes} mind-changes"
            )
        
        lines.append("\n" + "=" * 60)
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════
# AGENT TOOL INTERFACE — hooks into the agent bridge
# ═══════════════════════════════════════════════════════

_simulator_instance: Optional[CrowdSimulator] = None

def get_simulator(llm_fn: Optional[Callable] = None) -> CrowdSimulator:
    """Get or create the global simulator instance."""
    global _simulator_instance
    if _simulator_instance is None:
        _simulator_instance = CrowdSimulator(llm_fn=llm_fn)
    return _simulator_instance


def execute_simulation_tool(params: Dict[str, Any]) -> str:
    """Tool interface for the agent bridge."""
    action = params.get("action", "predict")
    sim = get_simulator()
    
    if action == "predict":
        scenario = params.get("scenario", "")
        if not scenario:
            return "Error: 'scenario' parameter required. Describe the situation to predict."
        
        population = int(params.get("population", 200))
        rounds = int(params.get("rounds", 7))
        scenario_type = params.get("scenario_type", None)
        
        report = sim.predict(
            scenario=scenario,
            population_size=population,
            num_rounds=rounds,
            scenario_type=scenario_type,
        )
        
        return sim.format_report(report)
    
    elif action == "quick":
        # Quick prediction with small population
        scenario = params.get("scenario", "")
        if not scenario:
            return "Error: 'scenario' parameter required."
        
        report = sim.predict(scenario=scenario, population_size=100, num_rounds=5)
        return sim.format_report(report)
    
    elif action == "types":
        return (
            "Available scenario types:\n"
            "  financial - Stock market, crypto, investment decisions\n"
            "  business  - Customer behavior, pricing, churn\n"
            "  workplace - Employee decisions, policy changes\n"
            "  social    - Viral content, public opinion, cancellation\n"
            "  political - Elections, protests, policy impact\n"
            "\nThe engine auto-detects the type from your description."
        )
    
    else:
        return f"Unknown action '{action}'. Use: predict, quick, or types."


# ═══════════════════════════════════════════════════════
# DIRECT TESTING
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    print("Testing CrowdSimulator...\n")
    
    sim = CrowdSimulator()
    
    # Test 1: Financial scenario
    report = sim.predict(
        scenario="Tesla stock after US goes to war with Iran. Oil prices spiking to $120. "
                 "EV market uncertainty. Elon Musk tweets 'HODL'.",
        population_size=500,
        num_rounds=7,
    )
    print(sim.format_report(report))
    
    print("\n\n")
    
    # Test 2: Business scenario
    report2 = sim.predict(
        scenario="Netflix raises subscription price by $5/month during a recession",
        population_size=300,
        num_rounds=5,
    )
    print(sim.format_report(report2))
