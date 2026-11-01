"""Reads the screen as `uiautomator dump` wrote it, for ui.sh. Standard library only.

Usage: ui_tree.py list <dump.xml>                 every element worth naming, one per line
       ui_tree.py find <dump.xml> <selector>      "<x> <y>" of the element's center, then a line
                                                  describing it; exit status 1 if there's none

A selector is text, matched in an element's text or description, or one field: text:<text>,
desc:<description>, id:<resource id>, class:<class name>. Text is matched without regard to case,
an element that holds exactly that first, else one that contains it. An id is the whole resource id,
or the part after ":id/". A class is the whole name or its last part. Of several matches, the first
on the screen in reading order wins, and a line on stderr says how many there were.
"""
import re
import sys
import xml.etree.ElementTree as ElementTree

BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
FLAGS = ("clickable", "long-clickable", "scrollable", "checkable", "checked", "selected", "focused")


class Element:
    def __init__(self, node):
        self.text = node.get("text", "")
        self.desc = node.get("content-desc", "")
        self.resource = node.get("resource-id", "")
        self.cls = node.get("class", "")
        self.flags = [flag for flag in FLAGS if node.get(flag) == "true"]
        self.enabled = node.get("enabled", "true") == "true"
        found = BOUNDS.fullmatch(node.get("bounds", ""))
        self.left, self.top, self.right, self.bottom = (int(n) for n in found.groups()) if found else (0, 0, 0, 0)

    @property
    def visible(self):
        return self.right > self.left and self.bottom > self.top

    @property
    def center(self):
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    @property
    def short_id(self):
        return self.resource.split(":id/", 1)[-1]

    @property
    def short_class(self):
        return self.cls.rsplit(".", 1)[-1]

    @property
    def worth_naming(self):
        return bool(self.text or self.desc or self.resource or self.flags)

    def __str__(self):
        parts = [self.short_class]
        if self.text:
            parts.append(repr(self.text))
        if self.desc:
            parts.append(f"desc={self.desc!r}")
        if self.resource:
            parts.append(f"id={self.short_id}")
        x, y = self.center
        parts.append(f"at {x},{y}")
        parts.append(f"size {self.right - self.left}x{self.bottom - self.top}")
        parts.extend(self.flags)
        if not self.enabled:
            parts.append("disabled")
        return " ".join(parts)


def elements(path):
    return [element for node in ElementTree.parse(path).iter("node")
            if (element := Element(node)).visible]


def matches(element, selector):
    """2 for an exact match, 1 for a partial one, 0 for none."""
    field, _, value = selector.partition(":")
    if field == "id" and value:
        return 2 if value in (element.resource, element.short_id) else 0
    if field == "class" and value:
        return 2 if value in (element.cls, element.short_class) else 0
    if field in ("text", "desc") and value:
        return text_match(element.text if field == "text" else element.desc, value)
    return max(text_match(element.text, selector), text_match(element.desc, selector))


def text_match(text, wanted):
    text, wanted = text.casefold(), wanted.casefold()
    return 2 if text == wanted else 1 if wanted in text else 0


def find(path, selector):
    found = [(score, element) for element in elements(path)
             if (score := matches(element, selector))]
    best = max((score for score, _ in found), default=0)
    found = [element for score, element in found if score == best]
    if not found:
        return 1
    found.sort(key=lambda element: (element.top, element.left))
    if len(found) > 1:
        print(f"{len(found)} elements match '{selector}'; using the first", file=sys.stderr)
    print(*found[0].center)
    print(found[0])
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "list":
        for element in elements(sys.argv[2]):
            if element.worth_naming:
                print(element)
        return 0
    if len(sys.argv) == 4 and sys.argv[1] == "find":
        return find(sys.argv[2], sys.argv[3])
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
