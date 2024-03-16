<img src="http://mypy-lang.org/static/mypy_light.svg" alt="mypy logo" width="300px"/>

# pytest plugin for testing mypy types, stubs, and plugins

[![Tests Status](https://github.com/typeddjango/pytest-mypy-plugins/actions/workflows/test.yml/badge.svg)](https://github.com/typeddjango/pytest-mypy-plugins/actions/workflows/test.yml)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Gitter](https://badges.gitter.im/mypy-django/Lobby.svg)](https://gitter.im/mypy-django/Lobby)
[![PyPI](https://img.shields.io/pypi/v/pytest-mypy-plugins?color=blue)](https://pypi.org/project/pytest-mypy-plugins/)
[![Conda Version](https://img.shields.io/conda/vn/conda-forge/pytest-mypy-plugins.svg?color=blue)](https://anaconda.org/conda-forge/pytest-mypy-plugins)

## Installation

This package is available on [PyPI](https://pypi.org/project/pytest-mypy-plugins/)

```bash
pip install pytest-mypy-plugins
```

and [conda-forge](https://anaconda.org/conda-forge/pytest-mypy-plugins)

```bash
conda install -c conda-forge pytest-mypy-plugins
```

## Usage

### Running

Plugin, after installation, is automatically picked up by `pytest` therefore it is sufficient to
just execute:

```bash
pytest
```

### Paths

The `PYTHONPATH` and `MYPYPATH` environment variables, if set, are passed to `mypy` on invocation.
This may be helpful if you are testing a local plugin and need to provide an import path to it.

Be aware that when `mypy` is run in a subprocess (the default) the test cases are run in temporary working directories
where relative paths such as `PYTHONPATH=./my_plugin` do not reference the directory which you are running `pytest` from.
If you encounter this, consider invoking `pytest` with `--mypy-same-process` or make your paths absolute,
e.g. `PYTHONPATH=$(pwd)/my_plugin pytest`.

You can also specify `PYTHONPATH`, `MYPYPATH`, or any other environment variable in `env:` section of `yml` spec:

```yml
- case: mypy_path_from_env
  main: |
    from pair import Pair

    instance: Pair
    reveal_type(instance)  # N: Revealed type is 'pair.Pair'
  env:
    - MYPYPATH=../fixtures
```


### What is a test case?

In general each test case is just an element in an array written in a properly formatted `YAML` file.
On top of that, each case must comply to following types:

| Property        | Type                                                   | Description                                                                                                         |
| --------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `case`          | `str`                                                  | Name of the test case, complies to `[a-zA-Z0-9]` pattern                                                            |
| `main`          | `str`                                                  | Portion of the code as if written in `.py` file                                                                     |
| `files`         | `Optional[List[File]]=[]`\*                            | List of extra files to simulate imports if needed                                                                   |
| `disable_cache` | `Optional[bool]=False`                                 | Set to `true` disables `mypy` caching                                                                               |
| `mypy_config`   | `Optional[str]`                                        | Inline `mypy` configuration, passed directly to `mypy` as `--config-file` option, possibly joined with `--mypy-pyproject-toml-file` or `--mypy-ini-file` contents if they are passed. By default is treated as `ini`, treated as `toml` only if `--mypy-pyproject-toml-file` is passed |
| `env`           | `Optional[Dict[str, str]]={}`                          | Environmental variables to be provided inside of test run                                                           |
| `parametrized`  | `Optional[List[Parameter]]=[]`\*                       | List of parameters, similar to [`@pytest.mark.parametrize`](https://docs.pytest.org/en/stable/parametrize.html)     |
| `skip`          | `str`                                                  | Expression evaluated with following globals set: `sys`, `os`, `pytest` and `platform`                               |
| `expect_fail`   | `bool`                                                 | Mark test case as an expected failure, like [`@pytest.mark.xfail`](https://docs.pytest.org/en/stable/skipping.html) |
| `regex`         | `str`                                                  | Allow regular expressions in comments to be matched against actual output. Defaults to "no", i.e. matches full text.|

(*) Appendix to **pseudo** types used above:

```python
class File:
    path: str
    content: Optional[str] = None
Parameter = Mapping[str, Any]
```

Implementation notes:

- `main` must be non-empty string that evaluates to valid **Python** code,
- `content` of each of extra files must evaluate to valid **Python** code,
- `parametrized` entries must all be the objects of the same _type_. It simply means that each
  entry must have **exact** same set of keys,
- `skip` - an expression set in `skip` is passed directly into
  [`eval`](https://docs.python.org/3/library/functions.html#eval). It is advised to take a peek and
  learn about how `eval` works.

Repository also offers a [JSONSchema](pytest_mypy_plugins/schema.json), with which
it validates the input. It can also offer your editor auto-completions, descriptions, and validation.

All you have to do, add the following line at the top of your YAML file:
```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/typeddjango/pytest-mypy-plugins/master/pytest_mypy_plugins/schema.json
```

### Example

#### 1. Inline type expectations

```yaml
# typesafety/test_request.yml
- case: request_object_has_user_of_type_auth_user_model
  main: |
    from django.http.request import HttpRequest
    reveal_type(HttpRequest().user)  # N: Revealed type is 'myapp.models.MyUser'
    # check that other fields work ok
    reveal_type(HttpRequest().method)  # N: Revealed type is 'Union[builtins.str, None]'
  files:
    - path: myapp/__init__.py
    - path: myapp/models.py
      content: |
        from django.db import models
        class MyUser(models.Model):
            pass
```

#### 2. `@parametrized`

```yaml
- case: with_params
  parametrized:
    - val: 1
      rt: builtins.int
    - val: 1.0
      rt: builtins.float
  main: |
    reveal_type({{ val }})  # N: Revealed type is '{{ rt }}'
```

Properties that you can parametrize:
- `main`
- `mypy_config`
- `out`

#### 3. Longer type expectations

```yaml
- case: with_out
  main: |
    reveal_type('abc')
  out: |
    main:1: note: Revealed type is 'builtins.str'
```

#### 4. Regular expressions in expectations

```yaml
- case: expected_message_regex_with_out
  regex: yes
  main: |
    a = 'abc'
    reveal_type(a)
  out: |
    main:2: note: .*str.*
```

#### 5. Regular expressions specific lines of output.

```yaml
- case: expected_single_message_regex
  main: |
    a = 'hello'
    reveal_type(a)  # NR: .*str.*
```

## Options

```
mypy-tests:
  --mypy-testing-base=MYPY_TESTING_BASE
                        Base directory for tests to use
  --mypy-pyproject-toml-file=MYPY_PYPROJECT_TOML_FILE
                        Which `pyproject.toml` file to use
                        as a default config for tests.
                        Incompatible with `--mypy-ini-file`
  --mypy-ini-file=MYPY_INI_FILE
                        Which `.ini` file to use as a default config for tests.
                        Incompatible with `--mypy-pyproject-toml-file`
  --mypy-same-process
                        Run in the same process. Useful for debugging,
                        will create problems with import cache
  --mypy-extension-hook=MYPY_EXTENSION_HOOK
                        Fully qualified path to the extension hook function,
                        in case you need custom yaml keys. Has to be top-level
  --mypy-only-local-stub
                        mypy will ignore errors from site-packages
  --mypy-closed-schema
                        Use closed schema to validate YAML test cases,
                        which won't allow any extra keys
                        (does not work well with `--mypy-extension-hook`)

```

## Configuration

For convenience, it is also possible to define a default `mypy` configuration in the root `pyproject.toml` file of your project:

```toml
[tool.pytest-mypy-plugins.mypy-config]
force_uppercase_builtins = true
force_union_syntax = true
```

The ultimate `mypy` configuration applied during a test is derived by merging the following sources (if they exist), in order:

1. The `mypy-config` table in the root `pyproject.toml` of the project.
2. The configuration file provided via `--mypy-pyproject-toml-file` or `--mypy-ini-file`.
3. The `config_mypy` field of the test case.

## Further reading

- [Testing mypy stubs, plugins, and types](https://sobolevn.me/2019/08/testing-mypy-types)

## License

[MIT](https://github.com/typeddjango/pytest-mypy-plugins/blob/master/LICENSE)
