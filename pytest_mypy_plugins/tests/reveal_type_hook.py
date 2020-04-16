from pytest_mypy_plugins.item import YamlTestItem


def hook(item: YamlTestItem) -> None:
    parsed_test_data = item.parsed_test_data
    obj_to_reveal = parsed_test_data.get("reveal_type")
    if obj_to_reveal:
        for file in item.files:
            if file.path.endswith("main.py"):
                file.content = f"reveal_type({obj_to_reveal})"
