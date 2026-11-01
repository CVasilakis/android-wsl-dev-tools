"""Made-up screens, as `uiautomator dump` writes them, for the fake adb's ui_hierarchy."""
from xml.sax.saxutils import quoteattr


def node(*children, text="", desc="", id="", cls="android.widget.TextView", bounds="[0,0][100,100]",
         **flags):
    """One element. `flags` are its attributes with _ for -, e.g. long_clickable="true"; a real
    dump has all of them, this one only those that matter."""
    attributes = {"text": text, "resource-id": id, "class": cls, "content-desc": desc,
                  "bounds": bounds, **{name.replace("_", "-"): value for name, value in flags.items()}}
    shown = " ".join(f"{name}={quoteattr(value)}" for name, value in attributes.items())
    return f"<node {shown}>{''.join(children)}</node>"


def hierarchy(*nodes):
    return ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            f'<hierarchy rotation="0">{"".join(nodes)}</hierarchy>')
