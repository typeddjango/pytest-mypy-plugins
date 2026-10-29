def format_mismatched_line(line: str) -> str:
    return f"  {str(line):<45} (diff)"


def format_matched_line(line: str, width: int = 100) -> str:
    return f" {line[:width]}..." if len(line) > width else f" {line}"


def format_error_lines(lines: list[str]) -> str:
    return "\n".join(lines) if lines else "  (empty)"


def remove_empty_lines(lines: list[str]) -> list[str]:
    return list(filter(None, lines))
