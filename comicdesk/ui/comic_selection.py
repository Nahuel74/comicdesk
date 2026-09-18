"""Selection state that can survive replacement of the comic model."""


class ComicSelection:
    """Keep selection by comic identity rather than by transient row numbers."""

    def __init__(self):
        self._paths = set()

    @staticmethod
    def _key(comic):
        path = getattr(comic, "path", comic)
        return str(path)

    def remember(self, comics):
        """Store the identities in *comics* for restoration after a refresh."""
        self._paths = {self._key(comic) for comic in comics}

    def restore(self, comics):
        """Return matching comics in the order supplied by the current model."""
        restored = [comic for comic in comics if self._key(comic) in self._paths]
        self._paths = {self._key(comic) for comic in restored}
        return restored

    def clear(self):
        self._paths.clear()

    def remap_paths(self, mapping: dict[str, str]):
        """Replace remembered path keys after files are renamed on disk."""
        if not mapping:
            return
        self._paths = {mapping.get(path, path) for path in self._paths}

    def contains(self, comic):
        return self._key(comic) in self._paths

    @property
    def paths(self):
        return frozenset(self._paths)
