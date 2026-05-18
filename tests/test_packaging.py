import tomllib
from pathlib import Path


def load_pyproject():
    return tomllib.loads(Path("pyproject.toml").read_text())


def test_pyproject_declares_markdown_readme_and_spdx_license_for_pypi():
    project = load_pyproject()["project"]

    assert project["readme"] == {"file": "README.md", "content-type": "text/markdown"}
    assert project["license"] == "Apache-2.0"
    assert "License :: OSI Approved :: Apache Software License" not in project.get("classifiers", [])


def test_pyproject_exposes_single_agentbus_console_script():
    scripts = load_pyproject()["project"]["scripts"]

    assert scripts == {"agentbus": "agentbus.cli:main"}
