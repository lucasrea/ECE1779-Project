import json
import os

class SemanticCache:
    def __init__(self, cache_file='/app/cache/semantic_cache.json'):
        self.cache_file = cache_file
        self.cache = {}
        self._load_cache()

    def _load_cache(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.cache = {}

    def _save_cache(self):
        os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except IOError:
            pass  # Handle write errors gracefully

    def get(self, key):
        return self.cache.get(key)

    def set(self, key, value):
        self.cache[key] = value
        self._save_cache()

    def clear(self):
        self.cache.clear()
        self._save_cache()