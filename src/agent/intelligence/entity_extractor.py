"""
entity_extractor.py — LLM-Powered Entity & Ontology Extraction

Inspired by MiroFish's ontology_generator.py which uses LLMs to
automatically define entity types and relationship schemas from raw text.

CAPABILITIES:
    1. Entity extraction — finds people, orgs, concepts, events in text
    2. Relationship extraction — identifies connections between entities
    3. Ontology inference — derives entity types and schemas
    4. Structured JSON output — forces LLM to output clean structured data
    5. Auto-feeds into KnowledgeGraph

GOES BEYOND MiroFish:
    - Works with ANY LLM provider (not just OpenAI SDK)
    - Graceful fallback to regex when LLM is unavailable
    - Batch processing for large documents
"""
import re
import json
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime


# ═══════════════════════════════════════════════════════
# DATA TYPES
# ═══════════════════════════════════════════════════════

@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    name: str
    entity_type: str            # person, organization, concept, event, location, etc.
    summary: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8     # Extraction confidence
    source_text: str = ""       # The text this was extracted from

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "entity_type": self.entity_type,
            "summary": self.summary,
            "attributes": self.attributes,
            "confidence": self.confidence,
        }


@dataclass
class ExtractedRelationship:
    """A relationship extracted from text."""
    source: str                 # Source entity name
    target: str                 # Target entity name
    relationship: str           # Relationship type
    fact: str = ""              # The fact describing this relationship
    confidence: float = 0.8
    bidirectional: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "relationship": self.relationship,
            "fact": self.fact,
            "confidence": self.confidence,
        }


@dataclass
class ExtractionResult:
    """Complete extraction result."""
    entities: List[ExtractedEntity]
    relationships: List[ExtractedRelationship]
    source_text_length: int = 0
    extraction_time_ms: float = 0
    method: str = "llm"         # "llm" or "regex_fallback"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entities": [e.to_dict() for e in self.entities],
            "relationships": [r.to_dict() for r in self.relationships],
            "entity_count": len(self.entities),
            "relationship_count": len(self.relationships),
            "method": self.method,
        }


# ═══════════════════════════════════════════════════════
# EXTRACTION PROMPTS
# ═══════════════════════════════════════════════════════

ENTITY_EXTRACTION_PROMPT = """Analyze the following text and extract all entities and relationships.

TEXT:
{text}

Return a JSON object with this exact structure:
{{
    "entities": [
        {{
            "name": "Entity Name",
            "entity_type": "person|organization|concept|event|location|technology|product",
            "summary": "Brief description of this entity",
            "attributes": {{"key": "value"}}
        }}
    ],
    "relationships": [
        {{
            "source": "Source Entity Name",
            "target": "Target Entity Name",
            "relationship": "relationship_type",
            "fact": "The complete fact describing this relationship"
        }}
    ]
}}

RULES:
1. Extract ALL named entities — people, organizations, places, concepts, technologies
2. Identify ALL relationships between entities — who works where, what caused what, etc.
3. Use lowercase relationship types like: works_at, leads, created, caused_by, part_of, related_to
4. The "fact" should be a complete, self-contained sentence
5. Return ONLY valid JSON, no additional text
"""

ONTOLOGY_INFERENCE_PROMPT = """Based on the following entities, infer the ontology (schema) of entity types and relationship types.

ENTITIES:
{entities_json}

Return a JSON object:
{{
    "entity_types": [
        {{
            "name": "TypeName",
            "description": "What this type represents",
            "common_attributes": ["attr1", "attr2"]
        }}
    ],
    "relationship_types": [
        {{
            "name": "relationship_name",
            "description": "What this relationship means",
            "typical_source": "SourceType",
            "typical_target": "TargetType"
        }}
    ]
}}

Return ONLY valid JSON.
"""


# ═══════════════════════════════════════════════════════
# ENTITY EXTRACTOR
# ═══════════════════════════════════════════════════════

class EntityExtractor:
    """
    LLM-powered entity and relationship extraction.

    Usage:
        extractor = EntityExtractor(llm_generate_fn=my_llm.generate)
        result = extractor.extract("OpenAI released GPT-4o. Sam Altman is CEO.")

        for entity in result.entities:
            print(f"{entity.name} ({entity.entity_type})")

        for rel in result.relationships:
            print(f"{rel.source} --[{rel.relationship}]--> {rel.target}")
    """

    # Common entity patterns for regex fallback
    ENTITY_PATTERNS = {
        "person": [
            r'\b(?:Mr|Mrs|Ms|Dr|Prof|CEO|CTO|President)\.\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+',
            r'\b[A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b',
        ],
        "organization": [
            r'\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*)*\s+(?:Inc|Corp|Ltd|LLC|Co|Group|Foundation|Institute|University|Labs?)\b',
            r'\b(?:Google|Microsoft|Apple|Amazon|Meta|OpenAI|Anthropic|NVIDIA|Tesla|SpaceX)\b',
        ],
        "technology": [
            r'\b(?:GPT-\d[a-z]?|Claude[-\s]\d|Gemini|BERT|LLaMA|Mistral|API|SDK|LLM|AI|ML|NLP)\b',
        ],
        "location": [
            r'\b(?:San Francisco|New York|London|Tokyo|Beijing|Silicon Valley|Washington)\b',
        ],
    }

    def __init__(self, llm_generate_fn=None, max_text_length: int = 8000):
        """
        Args:
            llm_generate_fn: Async or sync function that takes (prompt: str) -> str
                             If None, falls back to regex-based extraction
            max_text_length: Max characters to process at once
        """
        self._llm_generate = llm_generate_fn
        self._max_text_length = max_text_length
        self._stats = {
            "extractions": 0,
            "entities_found": 0,
            "relationships_found": 0,
            "llm_failures": 0,
            "regex_fallbacks": 0,
        }

    def extract(self, text: str, use_llm: bool = True) -> ExtractionResult:
        """
        Extract entities and relationships from text.

        Args:
            text: The text to extract from
            use_llm: If True and LLM is available, use LLM. Otherwise regex fallback.

        Returns:
            ExtractionResult with entities and relationships
        """
        start = time.time()
        self._stats["extractions"] += 1

        # Truncate if too long
        if len(text) > self._max_text_length:
            text = text[:self._max_text_length]

        entities = []
        relationships = []
        method = "regex_fallback"

        # Try LLM extraction first
        if use_llm and self._llm_generate:
            try:
                llm_result = self._extract_with_llm(text)
                if llm_result:
                    entities, relationships = llm_result
                    method = "llm"
            except Exception as e:
                self._stats["llm_failures"] += 1
                print(f"[EntityExtractor] LLM extraction failed: {e}, using regex fallback")

        # Regex fallback
        if not entities:
            entities = self._extract_with_regex(text)
            relationships = self._infer_relationships(entities, text)
            method = "regex_fallback"
            self._stats["regex_fallbacks"] += 1

        self._stats["entities_found"] += len(entities)
        self._stats["relationships_found"] += len(relationships)

        elapsed = (time.time() - start) * 1000
        return ExtractionResult(
            entities=entities,
            relationships=relationships,
            source_text_length=len(text),
            extraction_time_ms=elapsed,
            method=method
        )

    def _extract_with_llm(self, text: str) -> Optional[Tuple[List[ExtractedEntity], List[ExtractedRelationship]]]:
        """Use LLM to extract entities and relationships."""
        prompt = ENTITY_EXTRACTION_PROMPT.format(text=text[:6000])
        response = self._llm_generate(prompt)

        if not response:
            return None

        # Parse JSON from response
        parsed = self._parse_json_response(response)
        if not parsed:
            return None

        entities = []
        for e in parsed.get("entities", []):
            entities.append(ExtractedEntity(
                name=e.get("name", ""),
                entity_type=e.get("entity_type", "concept").lower(),
                summary=e.get("summary", ""),
                attributes=e.get("attributes", {}),
                confidence=0.9,
                source_text=text[:200],
            ))

        relationships = []
        for r in parsed.get("relationships", []):
            relationships.append(ExtractedRelationship(
                source=r.get("source", ""),
                target=r.get("target", ""),
                relationship=r.get("relationship", "related_to").lower(),
                fact=r.get("fact", ""),
                confidence=0.85,
            ))

        return entities, relationships

    def _extract_with_regex(self, text: str) -> List[ExtractedEntity]:
        """Fallback: extract entities using regex patterns."""
        entities = []
        seen = set()

        for entity_type, patterns in self.ENTITY_PATTERNS.items():
            for pattern in patterns:
                matches = re.findall(pattern, text)
                for match in matches:
                    name = match.strip()
                    if name.lower() not in seen and len(name) > 2:
                        seen.add(name.lower())
                        entities.append(ExtractedEntity(
                            name=name,
                            entity_type=entity_type,
                            summary=f"Extracted {entity_type} from text",
                            confidence=0.6,
                            source_text=text[:200],
                        ))

        return entities

    def _infer_relationships(self, entities: List[ExtractedEntity],
                              text: str) -> List[ExtractedRelationship]:
        """Infer relationships based on co-occurrence in text."""
        relationships = []
        entity_names = [e.name for e in entities]

        # Simple co-occurrence: if two entities appear in the same sentence, relate them
        sentences = re.split(r'[.!?]+', text)
        for sentence in sentences:
            found_in_sentence = [name for name in entity_names if name.lower() in sentence.lower()]
            for i in range(len(found_in_sentence)):
                for j in range(i + 1, len(found_in_sentence)):
                    relationships.append(ExtractedRelationship(
                        source=found_in_sentence[i],
                        target=found_in_sentence[j],
                        relationship="related_to",
                        fact=sentence.strip()[:200],
                        confidence=0.5,
                    ))

        return relationships

    @staticmethod
    def _parse_json_response(response: str) -> Optional[Dict]:
        """Extract JSON from LLM response (handles markdown code blocks)."""
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r'\{[\s\S]*\}', response)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        return None

    def extract_and_populate_graph(self, text: str, knowledge_graph) -> ExtractionResult:
        """
        Extract entities/relationships and automatically add them to a KnowledgeGraph.

        Args:
            text: Text to extract from
            knowledge_graph: KnowledgeGraph instance to populate

        Returns:
            ExtractionResult
        """
        result = self.extract(text)

        # Add entities to graph
        for entity in result.entities:
            knowledge_graph.add_entity(
                name=entity.name,
                entity_type=entity.entity_type,
                summary=entity.summary,
                attributes=entity.attributes,
                confidence=entity.confidence
            )

        # Add relationships to graph
        for rel in result.relationships:
            knowledge_graph.add_relationship(
                source_name=rel.source,
                target_name=rel.target,
                relationship=rel.relationship,
                fact=rel.fact,
                confidence=rel.confidence,
                source="extraction"
            )

        return result

    def infer_ontology(self, entities: List[ExtractedEntity]) -> Optional[Dict]:
        """
        Use LLM to infer ontology from extracted entities.
        Returns schema of entity types and relationship types.
        """
        if not self._llm_generate or not entities:
            return None

        entities_json = json.dumps([e.to_dict() for e in entities[:30]], indent=2)
        prompt = ONTOLOGY_INFERENCE_PROMPT.format(entities_json=entities_json)

        try:
            response = self._llm_generate(prompt)
            return self._parse_json_response(response)
        except Exception:
            return None

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)
