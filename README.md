<img src="http://mypy-lang.org/static/mypy_light.svg" alt="mypy logo" width="300px"/>

# pytest plugin for testing mypy types, stubs, and plugins

[![Build Status](https://travis-ci.org/typeddjango/pytest-mypy-plugins.svg?branch=master)](https://travis-ci.org/typeddjango/pytest-mypy-plugins)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)
[![Gitter](https://badges.gitter.im/mypy-django/Lobby.svg)](https://gitter.im/mypy-django/Lobby)

## Installation

```bash
pip install pytest-mypy-plugins
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
    - MYPYPATH=./pytest_mypy_plugins/tests/fixtures
```


### What is a test case?

In general each test case is just an element in an array written in a properly formatted `YAML` file.
On top of that, each case must comply to following types:

| Property        | Type                                                   | Description                                                                                                     |
| --------------- | ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `case`          | `str`                                                  | Name of the test case, complies to `[a-zA-Z0-9]` pattern                                                        |
| `main`          | `str`                                                  | Portion of the code as if written in `.py` file                                                                 |
| `files`         | `Optional[List[File]]=[]`\*                            | List of extra files to simulate imports if needed                                                               |
| `disable_cache` | `Optional[bool]=False`                                 | Set to `true` disables `mypy` caching                                                                           |
| `mypy_config`   | `Optional[Dict[str, Union[str, int, bool, float]]]={}` | Inline `mypy` configuration, passed directly to `mypy` as `--config-file` option                                |
| `env`           | `Optional[Dict[str, str]]={}`                          | Environmental variables to be provided inside of test run                                                       |
| `parametrized`  | `Optional[List[Parameter]]=[]`\*                       | List of parameters, similar to [`@pytest.mark.parametrize`](https://docs.pytest.org/en/stable/parametrize.html) |
| `skip`          | `str`                                                  | Expression evaluated with following globals set: `sys`, `os`, `pytest` and `platform`                           |

Appendix to **pseudo** types used above:

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
    reveal_type({[ val }})  # N: Revealed type is '{{ rt }}'
```

#### 3. Longer type expectations

```yaml
- case: with_out
  main: |
    reveal_type('str')
  out: |
    main:1: note: Revealed type is 'builtins.str'
```

## Options

```
mypy-tests:
  --mypy-testing-base=MYPY_TESTING_BASE
                        Base directory for tests to use
  --mypy-ini-file=MYPY_INI_FILE
                        Which .ini file to use as a default config for tests
  --mypy-same-process
                        Now, to help with various issues in django-stubs, it runs every single test in the subprocess mypy call.
                        Some debuggers cannot attach to subprocess, so enable this flag to make mypy check happen in the same process.
                        (Could cause cache issues)
```

## Further reading

- [Testing mypy stubs, plugins, and types](https://sobolevn.me/2019/08/testing-mypy-types)

## License

[MIT](https://github.com/typeddjango/pytest-mypy-plugins/blob/master/LICENSE)
