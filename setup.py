from setuptools import setup

setup(
    name='pytest-mypy-plugins',
    version='0.1.0',
    packages=['pytest_mypy'],
    # the following makes a plugin available to pytest
    entry_points={
        'pytest11': [
            'pytest-mypy-plugins = pytest_mypy.collect'
        ]
    },
    install_requires=[
        'pytest',
        'mypy',
        'decorator',
        'dataclasses',
        'capturer'
    ],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7'
    ]
)
