# Version history


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
