"""Deliberately flawed code for review demonstrations; do not import in production."""


def append_item(item, items=[]):
    items.append(item)
    print("Added item")
    return items
