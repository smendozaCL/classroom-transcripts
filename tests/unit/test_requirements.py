import os
import pytest
from pathlib import Path
import re


def parse_requirements(file_path):
    """Parse requirements.txt and return a dict of package names and versions."""
    requirements = {}
    current_package = None

    with open(file_path) as f:
        for line in f:
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Handle package lines
            if not line.startswith(" "):
                # Extract package name and version
                match = re.match(r"^([^=<>]+)([=<>]+.+)?$", line)
                if match:
                    package = match.group(1).strip()
                    version = match.group(2).strip() if match.group(2) else None
                    requirements[package] = version
                    current_package = package

            # Handle dependency comments
            elif line.startswith("    #"):
                if current_package and current_package in requirements:
                    comment = line.strip("# ").strip()
                    if "via" in comment:
                        requirements[current_package] = {
                            "version": requirements[current_package],
                            "via": [
                                dep.strip()
                                for dep in comment.replace("via", "").strip().split(",")
                            ],
                        }

    return requirements


def test_requirements_file_exists():
    """Test that requirements.txt exists in the functions directory."""
    req_file = Path("src/functions/requirements.txt")
    assert req_file.exists(), "requirements.txt not found in src/functions/"


def test_core_dependencies():
    """Test that core dependencies are present with correct versions."""
    requirements = parse_requirements("src/functions/requirements.txt")

    # Test core dependencies
    core_deps = {
        "azure-functions": {"min_version": "1.21"},
        "azure-storage-blob": {"min_version": "12.24"},
        "azure-identity": {"min_version": "1.19"},
        "assemblyai": {"min_version": "0.37"},
        "azure-functions-durable": {"min_version": "1.2"},
    }

    for package, config in core_deps.items():
        assert package in requirements, (
            f"Required package {package} not found in requirements.txt"
        )

        if isinstance(requirements[package], dict):
            version = requirements[package]["version"]
        else:
            version = requirements[package]

        if version:
            # Extract version number
            version_match = re.search(r"[0-9.]+", version)
            if version_match:
                version_num = version_match.group()
                min_version = config["min_version"]
                assert version_num >= min_version, (
                    f"{package} version {version_num} is less than minimum required version {min_version}"
                )


def test_dependency_sources():
    """Test that dependencies are properly sourced."""
    requirements = parse_requirements("src/functions/requirements.txt")

    # Check direct dependencies from pyproject.toml
    direct_deps = [
        "azure-functions",
        "azure-storage-blob",
        "azure-identity",
        "assemblyai",
        "azure-functions-durable",
    ]

    for dep in direct_deps:
        assert dep in requirements, f"Direct dependency {dep} not found"
        if isinstance(requirements[dep], dict):
            assert "via" in requirements[dep], f"Dependency source not found for {dep}"
            assert "functions (pyproject.toml)" in requirements[dep]["via"], (
                f"{dep} should be sourced from pyproject.toml"
            )


def test_security_requirements():
    """Test that security-related packages are present and up-to-date."""
    requirements = parse_requirements("src/functions/requirements.txt")

    security_deps = {
        "cryptography": {"min_version": "44.0"},
        "certifi": {"min_version": "2025.1"},
        "urllib3": {"min_version": "2.3"},
        "requests": {"min_version": "2.32"},
    }

    for package, config in security_deps.items():
        assert package in requirements, (
            f"Security package {package} not found in requirements.txt"
        )

        if isinstance(requirements[package], dict):
            version = requirements[package]["version"]
        else:
            version = requirements[package]

        if version:
            # Extract version number
            version_match = re.search(r"[0-9.]+", version)
            if version_match:
                version_num = version_match.group()
                min_version = config["min_version"]
                assert version_num >= min_version, (
                    f"{package} version {version_num} is less than minimum required version {min_version}"
                )


def test_no_conflicting_dependencies():
    """Test that there are no conflicting package versions."""
    requirements = parse_requirements("src/functions/requirements.txt")

    # Check for any package with multiple versions
    package_versions = {}
    for package, value in requirements.items():
        if isinstance(value, dict):
            version = value["version"]
        else:
            version = value

        if version:
            version_match = re.search(r"[0-9.]+", version)
            if version_match:
                version_num = version_match.group()
                if package in package_versions:
                    assert version_num == package_versions[package], (
                        f"Conflicting versions found for {package}: "
                        f"{version_num} vs {package_versions[package]}"
                    )
                package_versions[package] = version_num


def test_requirements_generated_by_uv():
    """Test that requirements.txt was generated by uv."""
    with open("src/functions/requirements.txt") as f:
        first_lines = [next(f) for _ in range(2)]

    assert "# This file was autogenerated by uv" in first_lines[0], (
        "requirements.txt should be generated by uv"
    )
    assert "uv pip compile" in first_lines[1], (
        "requirements.txt should be generated using 'uv pip compile'"
    )
