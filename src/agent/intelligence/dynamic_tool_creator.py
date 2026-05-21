"""
dynamic_tool_creator.py — Self-Improving Tool Generator

When the agent realizes it lacks a capability to achieve a goal,
it uses this module to write the Python code for a new tool,
compiles it safely, and adds it to the Tool Registry dynamically.
"""
import os
import json
import importlib.util
from typing import Callable, Optional, Dict, List
import logging

from .react_loop import ToolDefinition


SYS_PROMPT = """You are an expert Python tool creator for an autonomous agent.
The agent needs a new tool to accomplish a specific task.

Write a SINGLE Python function that achieves this.
RULES:
1. The function MUST take exactly one argument: `params` (a dictionary).
2. The function MUST return a string (the tool's output observation).
3. Be robust: use try/except blocks and return error details as strings.
4. Import required standard libraries inside the function.
5. NO third-party libraries unless completely necessary.

Return ONLY a JSON object exactly matching this schema:
{
  "tool_name": "lower_snake_case_name",
  "description": "What the tool does",
  "parameters": {"param1": "description", "param2": "description"},
  "python_code": "def execute(params):\n    import os\n    return 'Success'"
}
"""

class DynamicToolCreator:
    """
    Generates, compiles, and loads standard Python tools on the fly.
    """
    def __init__(self, llm_fn: Callable, sandbox_dir: str = "src/agent/tools/dynamic"):
        self.llm_fn = llm_fn
        self.sandbox_dir = sandbox_dir
        self.logger = logging.getLogger("DynamicToolCreator")
        os.makedirs(self.sandbox_dir, exist_ok=True)
        # Ensure it's a package
        init_file = os.path.join(self.sandbox_dir, "__init__.py")
        if not os.path.exists(init_file):
            open(init_file, 'a').close()

    def request_tool(self, missing_capability: str, context: str = "") -> Optional[ToolDefinition]:
        """
        Ask the LLM to write a new tool for the missing capability.
        """
        prompt = (
            f"Missing Capability: {missing_capability}\n"
            f"Context: {context}\n\n"
            "Generate the necessary Python tool as JSON."
        )

        try:
            response = self.llm_fn(prompt + "\n\n" + SYS_PROMPT)
            
            # Simple JSON extraction
            start = response.find("{")
            end = response.rfind("}") + 1
            if start == -1 or end == 0:
                self.logger.error("Failed to parse tool JSON.")
                return None
                
            data = json.loads(response[start:end])
            
            name = data["tool_name"]
            desc = data["description"]
            params = data["parameters"]
            code = data["python_code"]
            
            return self._compile_and_load(name, desc, params, code)

        except Exception as e:
            self.logger.error(f"Failed to dynamically create tool: {e}")
            return None

    def _compile_and_load(self, name: str, desc: str, params: Dict[str, str], code: str) -> Optional[ToolDefinition]:
        """Save the code to a file, load it dynamically, and return a ToolDefinition."""
        safe_name = "".join(c for c in name if c.isalnum() or c == '_')
        filepath = os.path.join(self.sandbox_dir, f"{safe_name}.py")
        
        # Write code to file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f'"""\nDynamically generated tool: {safe_name}\nDescription: {desc}\n"""\n\n')
            f.write(code)
            
        # Dynamically load the module
        try:
            spec = importlib.util.spec_from_file_location(f"dynamic_tool_{safe_name}", filepath)
            if spec is None or spec.loader is None:
                return None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Find the execute function
            if not hasattr(module, 'execute'):
                self.logger.error(f"Dynamically generated tool {safe_name} missing 'execute' function.")
                return None
                
            execute_fn = getattr(module, 'execute')
            
            # Create ToolDefinition
            self.logger.info(f"Successfully compiled and loaded new dynamic tool: {safe_name}")
            return ToolDefinition(
                name=safe_name,
                description=desc,
                parameters=params,
                execute_fn=execute_fn
            )
            
        except Exception as e:
            self.logger.error(f"Failed to load dynamic tool {safe_name}: {e}")
            return None
