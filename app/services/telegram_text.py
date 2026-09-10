"""Plain-text Telegram output, bounded conservatively in UTF-16 units."""


def split_message(text: str, limit: int = 4000) -> list[str]:
    """Preserve text and line boundaries where possible, including long fields."""
    if limit < 2:
        raise ValueError("Message limit must be at least two UTF-16 units")
    chunks = []
    remaining = text
    while remaining:
        units = 0
        end = 0
        for character in remaining:
            width = 2 if ord(character) > 0xFFFF else 1
            if units + width > limit:
                break
            units += width
            end += 1
        if end < len(remaining):
            newline = remaining.rfind("\n", 0, end)
            if newline >= 0:
                end = newline + 1
        chunks.append(remaining[:end])
        remaining = remaining[end:]
    return chunks
