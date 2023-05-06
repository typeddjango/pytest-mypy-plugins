# Version history


## WIP

### Bugfixes

- Also include `mypy.ini` and `pytest.ini` to `sdist` package


## Version 1.11.1

### Bugfixes

- Adds `tests/` subfolder to `sdist` package


## Version 1.11.0

### Features

- Adds `python3.11` support and promise about `python3.12` support
- Removes `pkg_resources` to use `packaging` instead


## Version 1.10.1

### Bugfixes

- Removes unused depenencies for `python < 3.7`
- Fixes compatibility with pytest 7.2, broken due to a private import from
  `py._path`.


## Version 1.10.0

### Features

- Changes how `mypy>=0.970` handles `MYPYPATH`
- Bumps minimal `mypy` version to `mypy>=0.970`
- Drops `python3.6` support


## Version 1.9.3

### Bugfixes

- Fixes `DeprecationWarning` for using `py.LocalPath` for `pytest>=7.0` #89


## Version 1.9.2

### Bugfixes

- Removes usages of `distutils` #71
- Fixes multiline messages #66
- Fixes that empty output test cases was almost ignored #63
- Fixes output formatting for expected messages #66


## Version 1.9.1

## Bugfixes

- Fixes that `regex` and `dataclasses` dependencies were not listed in `setup.py`


## Version 1.9.0

## Features

- Adds `regex` support in matching test output
- Adds a flag for expected failures
- Replaces deprecated `pystache` with `chevron`

## Misc

- Updates `mypy`


## Version 1.8.0

We missed this released by mistake.


## Version 1.7.0

### Features

- Adds `--mypy-only-local-stub` CLI flag to ignore errors in site-packages


## Version 1.6.1

### Bugfixes

- Changes how `MYPYPATH` and `PYTHONPATH` are calcualted. We now expand `$PWD` variable and also include relative paths specified in `env:` section


## Version 1.6.0

### Features

- Adds `python3.9` support
- Bumps required version of `pytest` to `>=6.0`
- Bumps required version of `mypy` to `>=0.790`

### Misc

- Moves from Travis to Github Actions


## Version 1.5.0

### Features

- Adds `PYTHONPATH` and `MYPYPATH` special handling
