<img src="http://mypy-lang.org/static/mypy_light.svg" alt="mypy logo" width="300px"/>

# PyTest plugin for testing mypy custom plugins

[![Build Status](https://travis-ci.org/mkurnikov/pytest-mypy-plugins.svg?branch=master)](https://travis-ci.org/mkurnikov/pytest-mypy-plugins)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

Example of a test case:
```
[case my_test_case]
class MyClass:
    def method(self) -> str:
        pass
reveal_type(MyClass().method())  # E: Revealed type is 'builtins.str'
```

Options:
```
mypy-tests:
  --mypy-testing-base=MYPY_TESTING_BASE
                        Base directory for tests to use
  --mypy-ini-file=MYPY_INI_FILE
                        Which .ini file to use as a default config for tests
```

