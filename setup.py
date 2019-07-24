import sys

from setuptools import setup

with open('README.md', 'r') as f:
    readme = f.read()

dependencies = [
    'pytest',
    'mypy',
    'decorator',
    'capturer',
    'pyyaml'
]

setup(
    name='pytest-mypy-plugins',
    version='1.0.2',
    description='pytest plugin for writing tests for mypy plugins',
    long_description=readme,
    long_description_content_type='text/markdown',
    license='MIT',
    url="https://github.com/mkurnikov/pytest-mypy-plugins",
    author="Maksim Kurnikov",
    author_email="maxim.kurnikov@gmail.com",
    packages=['pytest_mypy'],
    # the following makes a plugin available to pytest
    entry_points={
        'pytest11': [
            'pytest-mypy-plugins = pytest_mypy.collect'
        ]
    },
    install_requires=dependencies,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ]
)
