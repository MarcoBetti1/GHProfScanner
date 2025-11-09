from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("github-scanner")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"
