import sys
from pathlib import Path

# Add phase_p_mvp to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from controller.controller import controller
from controller.trace import new_trace

if __name__ == "__main__":
    new_trace()
    question = "Under what conditions does the system transition from EVALUATE to FROZEN?"
    result = controller(question)
    print(result)
