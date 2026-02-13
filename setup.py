from setuptools import setup

with open("README.md") as f:
    readme = f.read()

dependencies = [
    "Jinja2",
    "decorator",
    "jsonschema",
    "mypy>=1.3",
    "packaging",
    "pytest>=7.0.0",
    "pyyaml",
    "regex",
    "tomlkit>=0.11",
]

setup(
    name="pytest-mypy-plugins",
    version="3.2.0",
    description="pytest plugin for writing tests for mypy plugins",
    long_description=readme,
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/TypedDjango/pytest-mypy-plugins",
    author="Maksim Kurnikov",
    author_email="maxim.kurnikov@gmail.com",
    maintainer="Nikita Sobolev",
    maintainer_email="mail@sobolevn.me",
    packages=["pytest_mypy_plugins"],
    # the following makes a plugin available to pytest
    entry_points={"pytest11": ["pytest-mypy-plugins = pytest_mypy_plugins.collect"]},
    install_requires=dependencies,
    python_requires=">=3.9",
    package_data={
        "pytest_mypy_plugins": ["py.typed", "schema.json"],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Typing :: Typed",
    ],
)
