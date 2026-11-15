# How to contribute

## Tutorials

If you want to start working on this project,
you will need to get familiar with these APIs:

- Writing a `pytest` [plugin](https://docs.pytest.org/en/stable/how-to/writing_plugins.html)
- Mypy [documentation](https://mypy.readthedocs.io/en/stable/) and [configuration file](https://mypy.readthedocs.io/en/stable/config_file.html) reference


## First steps

1. Fork [our repo](https://github.com/typeddjango/pytest-mypy-plugins), here's the [guide on forking](https://help.github.com/en/github/getting-started-with-github/fork-a-repo)
2. [Clone your new repo](https://help.github.com/en/github/creating-cloning-and-archiving-repositories/cloning-a-repository) (forked repo) to have a local copy of the code
3. Apply the required changes! See the sections below on how to work with the code
4. Send a Pull Request to our original repo. Here's [the helpful guide](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/creating-a-pull-request) on how to do that


## Dependencies

To install them you would need to run command:

```bash
make install
```

## Tests

We use `pytest`. To run all tests: `make unit`

To run only the mypy cache tests (used in the compatibility CI job): `make unit-cache`

## Type checks

We use `mypy` to run type checks on our code.
To use it:

```bash
make type-check
```

## Formatting and linting

Apply formatting with `black` and `isort`:

```bash
make format
```

Check formatting without modifying files:

```bash
make lint
```

## One magic command

Run `make test` to run everything we have: formatting checks, type checks, and tests.