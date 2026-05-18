"""AgentBus: NATS JetStream task bus for distributed agent programs."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

__all__ = ["__version__"]


def _version_from_pyproject() -> str:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    with pyproject.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


if (Path(__file__).resolve().parents[1] / "pyproject.toml").exists():
    __version__ = _version_from_pyproject()
else:
    try:
        __version__ = version("agentbus")
    except PackageNotFoundError:
        __version__ = "0+unknown"
