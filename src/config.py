"""
config.py

Production Configuration Loader.
Loads `config.yaml` and exposes typed settings.
"""
import os
import yaml
from typing import Dict, Any

class Config:
    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        config_path = os.path.join(os.getcwd(), "config.yaml")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found at {config_path}")
            
        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)
            
    @property
    def env(self) -> str:
        return self._config.get("env", "development")

    @property
    def email(self) -> Dict[str, Any]:
        return self._config.get("email", {})

    @property
    def paths(self) -> Dict[str, str]:
        return self._config.get("paths", {})
    
    @property
    def report(self) -> Dict[str, Any]:
        return self._config.get("report", {})

# Global Instance
config = Config()
