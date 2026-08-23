from __future__ import annotations

from textual.theme import Theme


_DEFAULT = "ansi_default"

# Textual normally assigns distinct ANSI colours to semantic roles, cursors, and
# scrollbars.  Keep every one of those roles on the terminal defaults; focus and
# selection are expressed through reverse video in CSS instead.
_TERMINAL_VARIABLES = {
    "ansi-background": _DEFAULT,
    "ansi-foreground": _DEFAULT,
    "block-cursor-background": _DEFAULT,
    "block-cursor-foreground": _DEFAULT,
    "block-cursor-text-style": "reverse",
    "block-cursor-blurred-background": _DEFAULT,
    "block-cursor-blurred-foreground": _DEFAULT,
    "block-cursor-blurred-text-style": "bold",
    "block-hover-background": _DEFAULT,
    "border": _DEFAULT,
    "border-blurred": _DEFAULT,
    "button-focus-text-style": "bold reverse",
    "footer-key-foreground": _DEFAULT,
    "input-cursor-background": _DEFAULT,
    "input-cursor-foreground": _DEFAULT,
    "input-cursor-text-style": "reverse",
    "input-selection-background": _DEFAULT,
    "input-selection-foreground": _DEFAULT,
    "link-background-hover": _DEFAULT,
    "link-color": _DEFAULT,
    "link-color-hover": _DEFAULT,
    "markdown-h1-color": _DEFAULT,
    "markdown-h2-color": _DEFAULT,
    "markdown-h3-color": _DEFAULT,
    "markdown-h4-color": _DEFAULT,
    "markdown-h5-color": _DEFAULT,
    "markdown-h6-color": _DEFAULT,
    "screen-selection-background": _DEFAULT,
    "screen-selection-foreground": _DEFAULT,
    "scrollbar": _DEFAULT,
    "scrollbar-active": _DEFAULT,
    "scrollbar-background": _DEFAULT,
    "scrollbar-background-active": _DEFAULT,
    "scrollbar-background-hover": _DEFAULT,
    "scrollbar-corner-color": _DEFAULT,
    "scrollbar-hover": _DEFAULT,
}

TERMINAL_THEME = Theme(
    name="dolctl-terminal",
    primary=_DEFAULT,
    secondary=_DEFAULT,
    warning=_DEFAULT,
    error=_DEFAULT,
    success=_DEFAULT,
    accent=_DEFAULT,
    foreground=_DEFAULT,
    background=_DEFAULT,
    surface=_DEFAULT,
    panel=_DEFAULT,
    boost=_DEFAULT,
    ansi=True,
    variables=_TERMINAL_VARIABLES,
)


TERMINAL_CSS = """
App,
Screen,
ModalScreen,
Container,
Vertical,
Horizontal,
Static,
Label,
RichLog,
ListView,
ListItem,
DataTable,
Input,
Select,
SelectCurrent,
SelectOverlay,
OptionList,
Checkbox,
Button {
    background: ansi_default;
    color: ansi_default;
}

* {
    scrollbar-background: ansi_default;
    scrollbar-background-hover: ansi_default;
    scrollbar-background-active: ansi_default;
    scrollbar-color: ansi_default;
    scrollbar-color-hover: ansi_default;
    scrollbar-color-active: ansi_default;
    scrollbar-corner-color: ansi_default;
}

Button {
    min-width: 10;
    height: 3;
    border: tall ansi_default;
    background: ansi_default;
    color: ansi_default;
}

Button:hover,
Button:focus,
Button.-active,
Button.-current {
    border: tall ansi_default;
    background: ansi_default;
    color: ansi_default;
    text-style: bold reverse;
    tint: transparent;
}

Button:disabled,
Button:disabled:hover {
    border: tall ansi_default;
    background: ansi_default;
    color: ansi_default;
    text-style: dim;
    tint: transparent;
}

Input,
Input:focus,
Input.-invalid,
Input.-invalid:focus,
SelectCurrent,
SelectCurrent:focus,
SelectOverlay,
OptionList,
OptionList:focus {
    border: tall ansi_default;
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

Input > .input--cursor,
Input > .input--selection {
    background: ansi_default;
    color: ansi_default;
    text-style: reverse;
}

Input > .input--placeholder,
Input > .input--suggestion {
    background: ansi_default;
    color: ansi_default;
    text-style: dim;
}

Select:focus > SelectCurrent,
Select > SelectOverlay:focus {
    border: tall ansi_default;
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

OptionList > .option-list--option-highlighted,
OptionList:focus > .option-list--option-highlighted,
SelectOverlay > .option-list--option-highlighted,
SelectOverlay:focus > .option-list--option-highlighted {
    background: ansi_default;
    color: ansi_default;
    text-style: reverse;
}

OptionList > .option-list--option-hover,
SelectOverlay > .option-list--option-hover {
    background: ansi_default;
    color: ansi_default;
    text-style: underline;
}

ListView,
ListView:focus {
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

ListView > ListItem,
ListView > ListItem.-hovered,
ListView > ListItem.-highlight,
ListView:focus > ListItem.-highlight {
    background: ansi_default;
    color: ansi_default;
}

ListView > ListItem.-hovered {
    text-style: underline;
}

ListView > ListItem.-highlight,
ListView:focus > ListItem.-highlight {
    text-style: bold reverse;
}

DataTable,
DataTable:focus,
DataTable > .datatable--header,
DataTable:ansi > .datatable--header,
DataTable > .datatable--even-row,
DataTable > .datatable--fixed,
DataTable > .datatable--cursor,
DataTable:focus > .datatable--cursor,
DataTable > .datatable--fixed-cursor,
DataTable:focus > .datatable--fixed-cursor,
DataTable > .datatable--header-cursor,
DataTable > .datatable--header-hover,
DataTable > .datatable--hover {
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

DataTable > .datatable--header,
DataTable:ansi > .datatable--header {
    text-style: bold underline;
}

DataTable > .datatable--cursor,
DataTable:focus > .datatable--cursor,
DataTable > .datatable--fixed-cursor,
DataTable:focus > .datatable--fixed-cursor {
    text-style: reverse;
}

DataTable > .datatable--hover {
    text-style: underline;
}

Checkbox,
Checkbox:focus,
Checkbox > .toggle--button,
Checkbox.-on > .toggle--button,
Checkbox > .toggle--label,
Checkbox:focus > .toggle--label {
    border: tall ansi_default;
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

Checkbox:focus > .toggle--label {
    text-style: reverse;
}

ModalScreen {
    background: ansi_default;
    color: ansi_default;
}
"""
