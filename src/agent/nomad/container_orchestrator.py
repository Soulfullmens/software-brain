"""
container_orchestrator.py — Nomad Docker Orchestrator

Gives the agent the ability to act as a Command Center, spinning up
and managing offline microservices via Docker (like Ollama, Kiwix, Qdrant).
"""
import subprocess
import json
import os
import time
from typing import Dict, List, Optional
import logging

class NomadOrchestrator:
    """Manages local Docker containers to provide offline tools."""
    def __init__(self):
        self.logger = logging.getLogger("NomadOrchestrator")
        self._check_docker_installed()

    def _check_docker_installed(self) -> bool:
        """Verify Docker is available on the host machine."""
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info(f"Docker detected: {result.stdout.strip()}")
                return True
        except FileNotFoundError:
            self.logger.warning("Docker is not installed or not in PATH. Nomad containers cannot be deployed.")
        return False

    def deploy_container(self, name: str, image: str, ports: Dict[int, int] = None, volumes: Dict[str, str] = None, env: Dict[str, str] = None) -> bool:
        """
        Deploy a specific offline tool container.
        """
        if self.is_running(name):
            self.logger.info(f"Container {name} is already running.")
            return True

        cmd = ["docker", "run", "-d", "--name", name, "--restart", "unless-stopped"]
        
        # Resource limits for safety (NemoClaw integration)
        cmd.extend(["--memory=2g", "--cpus=2.0"])

        if ports:
            for host_port, container_port in ports.items():
                cmd.extend(["-p", f"{host_port}:{container_port}"])
                
        if volumes:
            for host_dir, container_dir in volumes.items():
                os.makedirs(host_dir, exist_ok=True)
                cmd.extend(["-v", f"{host_dir}:{container_dir}"])
                
        if env:
            for k, v in env.items():
                cmd.extend(["-e", f"{k}={v}"])

        cmd.append(image)
        
        try:
            self.logger.info(f"Deploying {name} via Docker: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                self.logger.info(f"Successfully deployed {name}. ID: {result.stdout.strip()}")
                return True
            else:
                self.logger.error(f"Failed to deploy {name}: {result.stderr}")
                return False
        except Exception as e:
            self.logger.error(f"Docker execution error: {e}")
            return False

    def is_running(self, name: str) -> bool:
        """Check if a specific Nomad container is running."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", name],
                capture_output=True, text=True
            )
            return result.returncode == 0 and "true" in result.stdout.lower()
        except Exception:
            return False

    def stop_container(self, name: str) -> bool:
        """Stop and remove a container."""
        try:
            subprocess.run(["docker", "stop", name], capture_output=True)
            subprocess.run(["docker", "rm", name], capture_output=True)
            self.logger.info(f"Stopped and removed container: {name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to stop container {name}: {e}")
            return False

    # --- NOMAD PRESETS ---

    def deploy_kiwix(self, library_dir: str, port: int = 8080) -> bool:
        """Deploy Kiwix for offline Wikipedia/ZIM reading."""
        return self.deploy_container(
            name="nomad_kiwix",
            image="ghcr.io/kiwix/kiwix-serve:latest",
            ports={port: 8080},
            volumes={os.path.abspath(library_dir): "/data"}
        )

    def deploy_cyberchef(self, port: int = 8000) -> bool:
        """Deploy CyberChef for offline data encoding/decoding."""
        return self.deploy_container(
            name="nomad_cyberchef",
            image="mpepping/cyberchef:latest",
            ports={port: 8000}
        )
