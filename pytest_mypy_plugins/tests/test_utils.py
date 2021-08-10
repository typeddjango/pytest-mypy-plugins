# encoding=utf-8
from pytest_mypy_plugins import utils


def test_render_template_with_None_value() -> None:
    # Given
    template = "{{ a }} {{ b }}"
    data = {"a": None, "b": 99}

    # When
    actual = utils.render_template(template=template, data=data)

    # Then
    assert actual == "None 99"
