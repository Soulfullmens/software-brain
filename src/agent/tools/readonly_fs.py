"""
readonly_fs.py — Read-Only FileSystem Tool.

CAN: list, search, read, metadata, size analysis.
CANNOT: write, delete, move, rename.
NO destructive operations. Period.

Gated through SecurityKernel for path safety.
"""
import os, time, stat, mimetypes
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path


# File types that are safe to read (no executables, no binaries)
SAFE_READ_EXTENSIONS = {
    # Text
    ".txt", ".md", ".rst", ".log", ".csv", ".json", ".yaml", ".yml",
    ".xml", ".html", ".htm", ".css", ".toml", ".ini", ".cfg", ".conf",
    # Code
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".c", ".cpp", ".h",
    ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".lua",
    ".sh", ".bash", ".bat", ".ps1", ".sql",
    # Data
    ".env.example", ".gitignore", ".dockerignore", ".editorconfig",
}

# Max file size to read (prevent memory explosion)
MAX_READ_SIZE = 1_000_000  # 1MB


class ReadOnlyFS:
    """Read-only filesystem — perceive files without touching them."""
    
    name = "filesystem"
    description = "Read-only filesystem: list, search, read, metadata"
    
    def __init__(self, allowed_roots: List[str] = None):
        self._allowed_roots = allowed_roots or [os.path.expanduser("~")]
        self._action_log: List[Dict] = []
    
    def run(self, action: str, **kwargs) -> Any:
        dispatch = {
            "list_directory": lambda: self._list_dir(kwargs.get("path", "")),
            "read_file": lambda: self._read_file(kwargs.get("path", "")),
            "search_files": lambda: self._search(kwargs.get("path", ""), kwargs.get("pattern", "")),
            "get_file_info": lambda: self._file_info(kwargs.get("path", "")),
            "get_folder_size": lambda: self._folder_size(kwargs.get("path", "")),
            "find_large_files": lambda: self._find_large(kwargs.get("path", ""), kwargs.get("min_mb", 100)),
            "find_recent_files": lambda: self._find_recent(kwargs.get("path", ""), kwargs.get("hours", 24)),
            "tree": lambda: self._tree(kwargs.get("path", ""), kwargs.get("depth", 2)),
        }
        fn = dispatch.get(action)
        if not fn:
            return {"error": f"Unknown action: {action}", "available": list(dispatch.keys())}
        
        start = time.time()
        result = fn()
        elapsed = (time.time() - start) * 1000
        self._action_log.append({"action": action, "time": datetime.now().isoformat(), "ms": round(elapsed,1)})
        return result
    
    def _check_path(self, path: str) -> Optional[Dict]:
        """Verify path is safe to access."""
        if not path:
            return {"error": "No path provided"}
        abs_path = os.path.abspath(path)
        # Block system paths
        blocked = ["C:\\Windows", "C:\\Program Files", "C:\\ProgramData", "$RECYCLE.BIN"]
        for b in blocked:
            if abs_path.upper().startswith(b.upper()):
                return {"error": f"Access denied: system path '{b}'"}
        return None
    
    def _list_dir(self, path: str) -> Dict:
        err = self._check_path(path)
        if err: return err
        if not os.path.isdir(path):
            return {"error": f"Not a directory: {path}"}
        try:
            entries = []
            for name in sorted(os.listdir(path))[:200]:  # Cap at 200
                full = os.path.join(path, name)
                entry = {"name": name, "is_dir": os.path.isdir(full)}
                if not entry["is_dir"]:
                    try:
                        entry["size"] = os.path.getsize(full)
                        entry["ext"] = os.path.splitext(name)[1].lower()
                    except OSError:
                        pass
                entries.append(entry)
            return {"path": path, "count": len(entries), "entries": entries}
        except PermissionError:
            return {"error": f"Permission denied: {path}"}
        except Exception as e:
            return {"error": str(e)}
    
    def _read_file(self, path: str) -> Dict:
        err = self._check_path(path)
        if err: return err
        if not os.path.isfile(path):
            return {"error": f"Not a file: {path}"}
        
        ext = os.path.splitext(path)[1].lower()
        if ext not in SAFE_READ_EXTENSIONS and ext:
            return {"error": f"Unsafe file type: '{ext}'. Only text/code files allowed.",
                    "safe_types": list(SAFE_READ_EXTENSIONS)[:20]}
        
        size = os.path.getsize(path)
        if size > MAX_READ_SIZE:
            return {"error": f"File too large: {size/1_000_000:.1f}MB (max {MAX_READ_SIZE/1_000_000}MB)",
                    "hint": "Use get_file_info for metadata"}
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            lines = content.count('\n') + 1
            return {"path": path, "content": content, "size": size, "lines": lines, "encoding": "utf-8"}
        except Exception as e:
            return {"error": str(e)}
    
    def _search(self, path: str, pattern: str) -> Dict:
        err = self._check_path(path)
        if err: return err
        if not os.path.isdir(path):
            return {"error": f"Not a directory: {path}"}
        
        matches = []
        pattern_lower = pattern.lower()
        try:
            for root, dirs, files in os.walk(path):
                # Skip hidden/system dirs
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__', '.git')]
                for f in files:
                    if pattern_lower in f.lower():
                        full = os.path.join(root, f)
                        matches.append({"path": full, "name": f, "size": os.path.getsize(full)})
                        if len(matches) >= 50:
                            return {"matches": matches, "count": len(matches), "truncated": True}
        except Exception as e:
            return {"error": str(e)}
        return {"matches": matches, "count": len(matches), "pattern": pattern}
    
    def _file_info(self, path: str) -> Dict:
        err = self._check_path(path)
        if err: return err
        if not os.path.exists(path):
            return {"error": f"Not found: {path}"}
        try:
            st = os.stat(path)
            info = {
                "path": path, "name": os.path.basename(path),
                "is_dir": os.path.isdir(path), "size": st.st_size,
                "size_human": self._human_size(st.st_size),
                "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
                "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                "readonly": not os.access(path, os.W_OK),
            }
            if not info["is_dir"]:
                info["extension"] = os.path.splitext(path)[1]
                info["mime_type"] = mimetypes.guess_type(path)[0] or "unknown"
            return info
        except Exception as e:
            return {"error": str(e)}
    
    def _folder_size(self, path: str) -> Dict:
        err = self._check_path(path)
        if err: return err
        total = 0
        file_count = 0
        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                        file_count += 1
                    except OSError:
                        pass
            return {"path": path, "total_bytes": total, "size_human": self._human_size(total), "file_count": file_count}
        except Exception as e:
            return {"error": str(e)}
    
    def _find_large(self, path: str, min_mb: int = 100) -> Dict:
        err = self._check_path(path)
        if err: return err
        threshold = min_mb * 1_000_000
        large = []
        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules',)]
                for f in files:
                    full = os.path.join(root, f)
                    try:
                        size = os.path.getsize(full)
                        if size > threshold:
                            large.append({"path": full, "size": size, "size_human": self._human_size(size)})
                    except OSError:
                        pass
                    if len(large) >= 50:
                        break
            large.sort(key=lambda x: -x["size"])
            return {"files": large, "count": len(large), "threshold_mb": min_mb}
        except Exception as e:
            return {"error": str(e)}
    
    def _find_recent(self, path: str, hours: int = 24) -> Dict:
        err = self._check_path(path)
        if err: return err
        cutoff = time.time() - (hours * 3600)
        recent = []
        try:
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', '__pycache__')]
                for f in files:
                    full = os.path.join(root, f)
                    try:
                        mtime = os.path.getmtime(full)
                        if mtime > cutoff:
                            recent.append({"path": full, "modified": datetime.fromtimestamp(mtime).isoformat()})
                    except OSError:
                        pass
                    if len(recent) >= 50:
                        break
            recent.sort(key=lambda x: x["modified"], reverse=True)
            return {"files": recent, "count": len(recent), "hours": hours}
        except Exception as e:
            return {"error": str(e)}
    
    def _tree(self, path: str, depth: int = 2) -> Dict:
        err = self._check_path(path)
        if err: return err
        lines = []
        self._tree_recurse(path, "", depth, lines)
        return {"path": path, "tree": "\n".join(lines[:200]), "depth": depth}
    
    def _tree_recurse(self, path: str, prefix: str, depth: int, lines: List[str]):
        if depth < 0 or len(lines) > 200:
            return
        try:
            entries = sorted(os.listdir(path))[:30]
            dirs = [e for e in entries if os.path.isdir(os.path.join(path, e)) and not e.startswith('.')]
            files = [e for e in entries if os.path.isfile(os.path.join(path, e))]
            for f in files[:15]:
                lines.append(f"{prefix}├── {f}")
            for d in dirs:
                lines.append(f"{prefix}├── {d}/")
                self._tree_recurse(os.path.join(path, d), prefix + "│   ", depth - 1, lines)
        except PermissionError:
            lines.append(f"{prefix}├── [PERMISSION DENIED]")
    
    @staticmethod
    def _human_size(size: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"
