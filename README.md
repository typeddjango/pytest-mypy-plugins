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

Examples of a test case:

```yaml
# typesafety/test_request.yml
-   case: request_object_has_user_of_type_auth_user_model
    disable_cache: true
    main: |
        from django.http.request import HttpRequest
        reveal_type(HttpRequest().user)  # N: Revealed type is 'myapp.models.MyUser'
        # check that other fields work ok
        reveal_type(HttpRequest().method)  # N: Revealed type is 'Union[builtins.str, None]'
    files:
        -   path: myapp/__init__.py
        -   path: myapp/models.py
            content: |
                from django.db import models
                class MyUser(models.Model):
                    pass
```

Running:

```bash
pytest
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
