<img src="http://mypy-lang.org/static/mypy_light.svg" alt="mypy logo" width="300px"/>

# PyTest plugin for testing mypy custom plugins

[![Build Status](https://travis-ci.org/mkurnikov/pytest-mypy-plugins.svg?branch=master)](https://travis-ci.org/mkurnikov/pytest-mypy-plugins)
[![Checked with mypy](http://www.mypy-lang.org/static/mypy_badge.svg)](http://mypy-lang.org/)

Examples of a test case:
```
[case my_test_case]
class MyClass:
    def method(self) -> str:
        pass
reveal_type(MyClass().method())  # E: Revealed type is 'builtins.str'
```
```
[CASE myTestCase]
[disable_cache]
[env DJANGO_SETTINGS_MODULE=settings]

print('hello, world)

[/CASE]
```

Options:
```
mypy-tests:
  --mypy-testing-base=MYPY_TESTING_BASE
                        Base directory for tests to use
  --mypy-ini-file=MYPY_INI_FILE
                        Which .ini file to use as a default config for tests
```

## Documentation

### General structure

Test case starts with the
```
[case my_test]
```
where `my_test` is a name of test. It could be camelCase or snake_case, no need for the `test_` prefix. `case` keyword could be uppercased `CASE` too, if it helps readability.

Test case could optionally end with
```
[/case]
```
(or `[/CASE]`)
if it helps readability.

All text between `case` delimiters is a code for a `main.py` file, except for special sections.

### Sections

Format is
```
[SECTION_NAME( SECTION_ATTRS)?]
```