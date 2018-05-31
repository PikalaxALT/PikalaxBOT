import json
import os


class Settings:
    categories = ('credentials', 'meta', 'user')

    def __init__(self, fname='settings.json'):
        self.fname = fname
        self.data: dict = {}

    def __enter__(self):
        self.fetch()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.commit()
        self.data = {}

    def commit(self):
        with open(self.fname, 'w') as fp:
            json.dump(self.data, fp, separators=(', ', ': '), indent=4)

    def fetch(self):
        mode = 'r' if os.path.exists(self.fname) else 'w+'
        if os.path.dirname(self.fname) and not os.path.exists(os.path.dirname(self.fname)):
            os.makedirs(os.path.dirname(self.fname), exist_ok=True)
        with open(self.fname, mode=mode) as fp:
            self.data = json.load(fp)
        for group in self.categories:
            self.data.setdefault(group, {})
        self.setdefault('user', 'markov_channels', [])
        self.setdefault('user', 'game', '!pikahelp')
        self.setdefault('user', 'whitelist', [])
        self.setdefault('user', 'debug', False)
        self.setdefault('user', 'cooldown', 10)

    def set(self, group, key, value):
        assert group in self.categories
        self.data[group][key] = value
    
    def setdefault(self, group, key, value):
        assert group in self.categories
        self.data[group].setdefault(key, value)

    def get(self, group, key, default=None):
        assert group in self.categories
        return self.data[group].get(key, default)

    def items(self, group):
        assert group in self.categories
        yield from self.data[group].items()

    def keys(self, group):
        assert group in self.categories
        yield from self.data[group].keys()

    def values(self, group):
        assert group in self.categories
        yield from self.data[group].values()
