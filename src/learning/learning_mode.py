from enum import Enum

class LearningMode(Enum):
    """
    Operational modes for the learning engine.
    
    This is the SINGLE SOURCE OF TRUTH for whether the agent can adapt.
    """
    LEARN = "learn"        # Normal operation: Accumulate pressure + Mutate
    EVALUATE = "evaluate"  # Dry run: Accumulate pressure, NO Mutation (Observe only)
    FROZEN = "frozen"      # Locked: No accumulation, No mutation (Production safety)
