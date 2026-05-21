"""
Text Perceiver - Deterministic Translation

Translates structured text input events into Claims.
Constraint: No learning, no memory access, no belief access.
"""

from typing import List, Optional
from datetime import datetime

from src.cognition.claim import Claim
from src.perception.input_event import InputEvent


class TextPerceiver:
    """
    Translates trusted text inputs into claims.
    Assumes payload is already structured JSON-like data.
    """
    
    def perceive(self, event: InputEvent) -> List[Claim]:
        """
        Convert an input event into a list of Claims.
        Returns empty list if modality is not 'text' or payload is invalid.
        """
        if event.modality != "text":
            return []
            
        payload = event.payload
        claims = []
        
        # Determine strict type
        msg_type = payload.get("type", "unknown")
        
        if msg_type == "entity":
            claim = self._parse_entity_payload(payload, event)
            if claim:
                claims.append(claim)
                
        elif msg_type == "relation":
            claim = self._parse_relation_payload(payload, event)
            if claim:
                claims.append(claim)
                
        elif msg_type == "prediction_confirmation":
            # Special case: Evidence confirming a prediction
            # This is how we close the prediction loop via input
            # Not a belief claim per se?
            # Actually, "Prediction Confirmation" is an EVIDENCE claim about something.
            # But integration.py treats claims as Entity or Relation.
            # We defer Prediction updates to PredictionManager resolution.
            # But how does input TRIGGER resolution?
            # For now, we only handle Entity/Relation claims.
            pass
            
        return claims

    def _parse_entity_payload(self, payload: dict, event: InputEvent) -> Optional[Claim]:
        """Parse entity data."""
        target_id = payload.get("target_id")
        if not target_id:
            return None
            
        confidence = float(payload.get("confidence", 0.5))
        content = payload.get("content", f"Entity {target_id}")
        
        # Pass through remaining data as claim payload
        claim_payload = {k: v for k, v in payload.items() if k not in ["type", "target_id", "confidence", "content"]}
        
        return Claim(
            type="entity",
            content=content,
            target_id=target_id,
            confidence=confidence,
            source=event.source,
            timestamp=event.timestamp,
            payload=claim_payload
        )

    def _parse_relation_payload(self, payload: dict, event: InputEvent) -> Optional[Claim]:
        """Parse relation data."""
        # For relations, target_id is the relation ID (if exists) or we constructs one?
        # Relation needs unique ID. Payload must provide it?
        # Or Integration handles it?
        # Integration expects target_id to be relation ID.
        target_id = payload.get("target_id")
        if not target_id:
             return None

        confidence = float(payload.get("confidence", 0.5))
        content = payload.get("content", "Relation")
        
        claim_payload = {k: v for k, v in payload.items() if k not in ["type", "target_id", "confidence", "content"]}
        
        return Claim(
            type="relation",
            content=content,
            target_id=target_id,
            confidence=confidence,
            source=event.source,
            timestamp=event.timestamp,
            payload=claim_payload
        )
