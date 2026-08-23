from __future__ import annotations

from textual.theme import Theme


ANSI_16_COLOURS = frozenset(
    {
        "ansi_black",
        "ansi_red",
        "ansi_green",
        "ansi_yellow",
        "ansi_blue",
        "ansi_magenta",
        "ansi_cyan",
        "ansi_white",
        "ansi_bright_black",
        "ansi_bright_red",
        "ansi_bright_green",
        "ansi_bright_yellow",
        "ansi_bright_blue",
        "ansi_bright_magenta",
        "ansi_bright_cyan",
        "ansi_bright_white",
    }
)

_DEFAULT = "ansi_default"

# These are terminal palette slots, not fixed RGB colours. Backgrounds stay on
# the terminal default while structure and state use the user's ANSI 16 palette.
_TERMINAL_VARIABLES = {
    "ansi-background": _DEFAULT,
    "ansi-foreground": _DEFAULT,
    "block-cursor-background": "ansi_blue",
    "block-cursor-foreground": "ansi_bright_white",
    "block-cursor-text-style": "bold",
    "block-cursor-blurred-background": _DEFAULT,
    "block-cursor-blurred-foreground": "ansi_cyan",
    "block-cursor-blurred-text-style": "bold",
    "block-hover-background": _DEFAULT,
    "border": "ansi_blue",
    "border-blurred": "ansi_bright_black",
    "button-focus-text-style": "bold reverse",
    "footer-key-foreground": "ansi_cyan",
    "input-cursor-background": _DEFAULT,
    "input-cursor-foreground": _DEFAULT,
    "input-cursor-text-style": "reverse",
    "input-selection-background": "ansi_blue",
    "input-selection-foreground": "ansi_bright_white",
    "link-background-hover": _DEFAULT,
    "link-color": "ansi_cyan",
    "link-color-hover": "ansi_bright_cyan",
    "markdown-h1-color": "ansi_bright_cyan",
    "markdown-h2-color": "ansi_cyan",
    "markdown-h3-color": "ansi_blue",
    "markdown-h4-color": "ansi_magenta",
    "markdown-h5-color": "ansi_bright_magenta",
    "markdown-h6-color": "ansi_bright_black",
    "screen-selection-background": "ansi_blue",
    "screen-selection-foreground": "ansi_bright_white",
    "scrollbar": "ansi_blue",
    "scrollbar-active": "ansi_bright_cyan",
    "scrollbar-background": _DEFAULT,
    "scrollbar-background-active": _DEFAULT,
    "scrollbar-background-hover": _DEFAULT,
    "scrollbar-corner-color": _DEFAULT,
    "scrollbar-hover": "ansi_cyan",
}

TERMINAL_THEME = Theme(
    name="dolctl-ansi16",
    primary="ansi_cyan",
    secondary="ansi_blue",
    warning="ansi_yellow",
    error="ansi_red",
    success="ansi_green",
    accent="ansi_magenta",
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
    scrollbar-color: ansi_blue;
    scrollbar-color-hover: ansi_cyan;
    scrollbar-color-active: ansi_bright_cyan;
    scrollbar-corner-color: ansi_default;
}

.section-title,
.modal-title {
    color: ansi_bright_cyan;
    text-style: bold;
}

.hint,
#root-context,
#keybar {
    color: ansi_bright_black;
}

.form-error {
    color: ansi_bright_red;
    text-style: bold;
}

Button {
    min-width: 8;
    height: 1;
    padding: 0 1;
    border: none;
    background: ansi_default;
    color: ansi_blue;
    text-style: bold;
}

Button:hover {
    border: none;
    background: ansi_blue;
    color: ansi_black;
    text-style: bold;
}

Button:focus,
Button.-active {
    border: none;
    background: ansi_bright_blue;
    color: ansi_black;
    text-style: bold;
    tint: transparent;
}

Button.action-primary {
    border: none;
    background: ansi_green;
    color: ansi_black;
    text-style: bold;
}

Button.action-primary:hover,
Button.action-primary:focus,
Button.action-primary.-active {
    border: none;
    background: ansi_bright_green;
    color: ansi_black;
}

Button.action-accent {
    border: none;
    background: ansi_default;
    color: ansi_cyan;
}

Button.action-accent:hover,
Button.action-accent:focus,
Button.action-accent.-active {
    border: none;
    background: ansi_cyan;
    color: ansi_black;
}

Button.action-danger {
    border: none;
    background: ansi_default;
    color: ansi_red;
}

Button.action-danger:hover,
Button.action-danger:focus,
Button.action-danger.-active {
    border: none;
    background: ansi_red;
    color: ansi_black;
}

Button:disabled,
Button:disabled:hover {
    border: none;
    background: ansi_default;
    color: ansi_bright_black;
    text-style: dim;
    tint: transparent;
}

Button.nav-button,
Button.subnav-button {
    height: 1;
    min-width: 12;
    padding: 0 1;
    border: none;
    color: ansi_bright_black;
    text-align: left;
}

Button.nav-button:hover,
Button.subnav-button:hover {
    border: none;
    color: ansi_cyan;
    text-style: bold;
}

Button.nav-button:focus,
Button.subnav-button:focus {
    border: none;
    color: ansi_bright_cyan;
    text-style: bold reverse;
}

Button.nav-button.-current,
Button.subnav-button.-current {
    border: none;
    background: ansi_blue;
    color: ansi_black;
    text-style: bold;
}

Input,
SelectCurrent,
SelectOverlay,
OptionList {
    border: tall ansi_bright_black;
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

Input:focus,
Select:focus > SelectCurrent,
Select > SelectOverlay:focus,
OptionList:focus {
    border: tall ansi_cyan;
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

Input.-invalid,
Input.-invalid:focus {
    border: tall ansi_red;
}

Input > .input--cursor {
    background: ansi_default;
    color: ansi_default;
    text-style: reverse;
}

Input > .input--selection {
    background: ansi_blue;
    color: ansi_bright_white;
}

Input > .input--placeholder,
Input > .input--suggestion {
    background: ansi_default;
    color: ansi_bright_black;
    text-style: dim;
}

OptionList > .option-list--option-highlighted,
SelectOverlay > .option-list--option-highlighted {
    background: ansi_default;
    color: ansi_cyan;
    text-style: bold;
}

OptionList:focus > .option-list--option-highlighted,
SelectOverlay:focus > .option-list--option-highlighted {
    background: ansi_blue;
    color: ansi_black;
    text-style: bold;
}

OptionList > .option-list--option-hover,
SelectOverlay > .option-list--option-hover {
    background: ansi_default;
    color: ansi_bright_cyan;
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
    color: ansi_cyan;
    text-style: underline;
}

ListView > ListItem.-highlight {
    color: ansi_cyan;
    text-style: bold;
}

ListView:focus > ListItem.-highlight {
    background: ansi_blue;
    color: ansi_black;
    text-style: bold;
}

DataTable,
DataTable:focus,
DataTable > .datatable--even-row,
DataTable > .datatable--fixed {
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

DataTable > .datatable--header,
DataTable:ansi > .datatable--header {
    background: ansi_default;
    color: ansi_bright_cyan;
    text-style: bold underline;
}

DataTable > .datatable--cursor,
DataTable > .datatable--fixed-cursor {
    background: ansi_default;
    color: ansi_cyan;
    text-style: bold;
}

DataTable:focus > .datatable--cursor,
DataTable:focus > .datatable--fixed-cursor {
    background: ansi_blue;
    color: ansi_black;
    text-style: bold;
}

DataTable > .datatable--header-cursor,
DataTable > .datatable--header-hover,
DataTable > .datatable--hover {
    background: ansi_default;
    color: ansi_bright_cyan;
    text-style: underline;
}

Checkbox,
Checkbox:focus,
Checkbox > .toggle--button,
Checkbox > .toggle--label {
    border: tall ansi_bright_black;
    background: ansi_default;
    color: ansi_default;
    background-tint: transparent;
}

Checkbox.-on > .toggle--button {
    color: ansi_bright_green;
    text-style: bold;
}

Checkbox:focus {
    border: tall ansi_cyan;
}

Checkbox:focus > .toggle--label {
    color: ansi_bright_cyan;
    text-style: bold reverse;
}

ModalScreen {
    background: ansi_default;
    color: ansi_default;
}

ModalScreen Label {
    color: ansi_yellow;
}

ModalScreen > Vertical {
    border: round ansi_blue;
    border-title-color: ansi_yellow;
    border-title-background: ansi_default;
    border-title-style: bold;
}
"""
