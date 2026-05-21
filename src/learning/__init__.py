"""
Layer 4: Learning Engine

This package handles the adaptation of belief formation policies.
It consumes signals (failures, surprises) and updates policies (trust, coefficients).

Also includes:
- FewShotLearner: Learn from 1-5 examples, recognize forever
- ContinualLearner: Gets smarter every interaction without retraining
"""

from .few_shot_learner import FewShotLearner, Prototype, RecognitionResult
from .continual_learner import ContinualLearner, LearningEvent, ConsolidationResult
