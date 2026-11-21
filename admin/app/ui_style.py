"""菜单 / 表格 / 表单样式配置，按登录用户保存，没存过的项取默认值。

- 默认值就是页面原本的外观；读到非法值一律按默认值，保存时非法值直接拒绝
- 内置超级管理员 id 为 0，同样存一行
- 生效方式：页面 <body> 上的 class 和 CSS 变量，由 body_attrs() 生成，样式见 static/css/dxCustom.css
- 表格：class 为 gs-*，变量为 --gs-*；表单：class 为 fs-*，变量为 --fs-*
"""
import re
from dataclasses import dataclass, field
from typing import Any, Callable

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _color(v: Any) -> bool:
    return isinstance(v, str) and (v == "" or COLOR_RE.match(v) is not None)


def _bool(v: Any) -> bool:
    return isinstance(v, bool)


def _one_of(*items: Any) -> Callable[[Any], bool]:
    # bool 是 int 的子类，数值枚举里要排除，免得 True 被当成 1
    return lambda v: not isinstance(v, bool) and v in items


def _int_range(min_value: int, max_value: int) -> Callable[[Any], bool]:
    return lambda v: isinstance(v, int) and not isinstance(v, bool) and min_value <= v <= max_value


@dataclass
class StyleKind:
    defaults: dict[str, Any]
    validators: dict[str, Callable[[Any], bool]]
    presets: dict[str, dict[str, Any]]
    body_attrs: Callable[[dict[str, Any]], dict[str, str]]
    fields: list[str] = field(init=False)

    def __post_init__(self):
        self.fields = list(self.defaults)

    def full_presets(self) -> dict[str, dict[str, Any]]:
        return {k: {"preset": k, **self.defaults, **o} for k, o in self.presets.items()}

    def valid(self, key: str, value: Any) -> bool:
        if key == "preset":
            return isinstance(value, str) and (value == "custom" or value in self.presets)
        check = self.validators.get(key)
        return bool(check and check(value))

    def merge(self, stored: dict[str, Any]) -> dict[str, Any]:
        values = dict(self.defaults)
        for key in self.defaults:
            if key in stored and self.valid(key, stored[key]):
                values[key] = stored[key]
        return values


# ───────────── 菜单 ─────────────
MENU_DEFAULTS = {"width": 150}
MENU_VALIDATORS = {"width": _int_range(120, 480)}


def menu_body_attrs(_s: dict[str, Any]) -> dict[str, str]:
    return {"class": "", "style": ""}


# ───────────── 表格 ─────────────
GRID_DENSITY = {"compact": "4px", "normal": "8px", "loose": "12px"}
GRID_HEADER_WEIGHT = {"bold": "600", "normal": "400"}
GRID_RADIUS = {"none": "0", "small": "4px", "large": "8px"}

GRID_DEFAULTS = {
    "preset": "default",
    "headerBg": "#f0f4f7",
    "headerFg": "",
    "columnLines": True,
    "rowLines": True,
    "stripe": True,
    "density": "compact",
    "pagerMode": "full",
    "pageSize": 20,
    "pagerInfo": True,
    "hoverRow": True,
    "hoverBg": "",
    "selectBg": "",
    "stripeBg": "",
    "fontSize": 13,
    "headerWeight": "bold",
    "headerHeight": "auto",
    "align": "default",
    "filterRow": True,
    "textOverflow": "ellipsis",
    "fixedCommand": True,
    "autoWidth": True,
    "showBorders": True,
    "radius": "small",
}

GRID_VALIDATORS = {
    **{k: _color for k in ("headerBg", "headerFg", "hoverBg", "selectBg", "stripeBg")},
    **{k: _bool for k in ("columnLines", "rowLines", "stripe", "pagerInfo", "hoverRow", "filterRow",
                          "fixedCommand", "autoWidth", "showBorders")},
    "density": _one_of(*GRID_DENSITY),
    "pagerMode": _one_of("compact", "full"),
    "pageSize": _one_of(10, 20, 50, 100, 500),
    "fontSize": _one_of(12, 13, 14),
    "headerWeight": _one_of(*GRID_HEADER_WEIGHT),
    "headerHeight": _one_of("auto", *GRID_DENSITY),
    "align": _one_of("default", "left"),
    "textOverflow": _one_of("ellipsis", "wrap"),
    "radius": _one_of(*GRID_RADIUS),
}

GRID_PRESETS = {
    "default": {},
    "classic": {"headerBg": "#CCE4F6", "headerFg": "#242424", "stripe": False, "density": "normal"},
    "dark": {"headerBg": "#33415c", "headerFg": "#ffffff", "columnLines": False, "density": "normal", "pagerMode": "compact"},
    "stripe": {"columnLines": False, "density": "normal", "pagerMode": "compact"},
    "compact": {"headerBg": "", "stripe": False, "pageSize": 50},
    "large": {"density": "normal", "fontSize": 14},
}


def grid_body_attrs(s: dict[str, Any]) -> dict[str, str]:
    classes: list[str] = []
    vars_: list[str] = []
    if s["headerBg"]:
        vars_.append(f"--gs-header-bg:{s['headerBg']}")
    if s["headerFg"]:
        vars_.append(f"--gs-header-fg:{s['headerFg']}")
    if s["density"] != "normal":
        vars_.append(f"--gs-pad-y:{GRID_DENSITY[s['density']]}")
    if s["stripe"]:
        classes.append("gs-stripe")
    for key, var in (("hoverBg", "--gs-hover-bg"), ("stripeBg", "--gs-stripe-bg")):
        if s[key]:
            vars_.append(f"{var}:{s[key]}")
    if s["selectBg"]:
        vars_.append(f"--gs-select-bg:{s['selectBg']}")
        classes.append("gs-select")
    if s["fontSize"] != GRID_DEFAULTS["fontSize"]:
        vars_.append(f"--gs-font-size:{s['fontSize']}px")
        classes.append("gs-font")
    if s["headerWeight"] != "bold":
        vars_.append(f"--gs-header-weight:{GRID_HEADER_WEIGHT[s['headerWeight']]}")
    if s["headerHeight"] != "auto":
        vars_.append(f"--gs-head-pad-y:{GRID_DENSITY[s['headerHeight']]}")
    if s["align"] == "left":
        classes.append("gs-align-left")
    if s["radius"] != "small":
        vars_.append(f"--gs-radius:{GRID_RADIUS[s['radius']]}")
    return {"class": " ".join(classes), "style": ";".join(vars_)}


# ───────────── 表单 ─────────────
FORM_ROW_GAP = {"compact": "2px", "normal": "5px", "loose": "10px"}
FORM_DENSITY = {"compact": "1px", "normal": "5px", "loose": "9px"}
FORM_RADIUS = {"none": "0", "small": "4px", "large": "8px"}
FORM_COLORS = {
    "labelColor": ("--fs-label-color", "fs-label-color"),
    "valueColor": ("--fs-value-color", "fs-value-color"),
    "inputBorder": ("--fs-input-border", "fs-border"),
    "inputFocus": ("--fs-input-focus", "fs-focus"),
    "inputBg": ("--fs-input-bg", "fs-bg"),
    "readonlyBg": ("--fs-readonly-bg", "fs-readonly-bg"),
    "panelBg": ("--fs-panel-bg", "fs-panel-bg"),
}

FORM_DEFAULTS = {
    "preset": "default",
    "labelAlign": "auto",
    "labelColor": "",
    "labelWeight": "auto",
    "fontSize": 0,
    "rowGap": "auto",
    "density": "auto",
    "radius": "auto",
    "inputBorder": "",
    "inputFocus": "",
    "inputBg": "",
    "readonlyBg": "",
    "valueColor": "",
    "panelBg": "",
}

FORM_VALIDATORS = {
    **{k: _color for k in FORM_COLORS},
    "labelAlign": _one_of("auto", "left", "right"),
    "labelWeight": _one_of("auto", "normal", "bold"),
    "fontSize": _one_of(0, 12, 13, 14),
    "rowGap": _one_of("auto", *FORM_ROW_GAP),
    "density": _one_of("auto", *FORM_DENSITY),
    "radius": _one_of("auto", *FORM_RADIUS),
}

FORM_PRESETS = {
    "default": {},
    "compact": {"labelAlign": "right", "rowGap": "compact", "density": "compact", "radius": "small", "inputBorder": "#9aa3b0"},
    "comfortable": {"labelAlign": "left", "rowGap": "loose", "density": "loose", "radius": "large"},
    "clear": {"labelColor": "#242424", "labelWeight": "bold", "inputBorder": "#616161"},
}


def form_body_attrs(s: dict[str, Any]) -> dict[str, str]:
    classes: list[str] = []
    vars_: list[str] = []
    if s["labelAlign"] != "auto":
        classes.append(f"fs-label-{s['labelAlign']}")
    if s["labelWeight"] != "auto":
        classes.append(f"fs-weight-{s['labelWeight']}")
    if s["fontSize"] != 0:
        vars_.append(f"--fs-font-size:{s['fontSize']}px")
        classes.append("fs-font")
    if s["rowGap"] != "auto":
        vars_.append(f"--fs-gap:{FORM_ROW_GAP[s['rowGap']]}")
        classes.append("fs-gap")
    if s["density"] != "auto":
        vars_.append(f"--fs-pad-y:{FORM_DENSITY[s['density']]}")
        classes.append("fs-pad")
        if s["density"] == "compact":
            classes.append("fs-compact")
    if s["radius"] != "auto":
        vars_.append(f"--fs-radius:{FORM_RADIUS[s['radius']]}")
        classes.append("fs-radius")
    for key, (var, cls) in FORM_COLORS.items():
        if s[key]:
            vars_.append(f"{var}:{s[key]}")
            classes.append(cls)
    return {"class": " ".join(classes), "style": ";".join(vars_)}


KINDS: dict[str, StyleKind] = {
    "menu": StyleKind(MENU_DEFAULTS, MENU_VALIDATORS, {}, menu_body_attrs),
    "grid": StyleKind(GRID_DEFAULTS, GRID_VALIDATORS, GRID_PRESETS, grid_body_attrs),
    "form": StyleKind(FORM_DEFAULTS, FORM_VALIDATORS, FORM_PRESETS, form_body_attrs),
}
