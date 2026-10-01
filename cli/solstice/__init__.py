"""Summer Solstice factory CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("solstice")
except PackageNotFoundError:  # running from a source tree without install
    __version__ = "2.0.0.dev0"
