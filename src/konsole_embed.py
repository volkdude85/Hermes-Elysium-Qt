"""QTermWidget wrapper — embeds Konsole's native terminal engine (libqtermwidget6)
directly as a child widget of a PySide6 container. Same terminal, same profile,
same rendering as Konsole itself."""

import ctypes
import os
from pathlib import Path
from typing import Optional

from PySide6 import QtCore, QtGui, QtWidgets

import profile_loader

# Load the C++ bridge
_so_path = Path(__file__).parent / "qtermwidget_bridge.so"
if not _so_path.exists():
    raise RuntimeError(f"qtermwidget_bridge.so not found at {_so_path} — compile it first")

_lib = ctypes.CDLL(str(_so_path))

# void* qtermwidget_create(void* parent_ptr, int start_shell)
_lib.qtermwidget_create.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.qtermwidget_create.restype = ctypes.c_void_p

# void qtermwidget_apply_profile(...)
_lib.qtermwidget_apply_profile.argtypes = [
    ctypes.c_void_p,          # widget_ptr
    ctypes.c_char_p,          # color_scheme
    ctypes.c_char_p,          # font_family
    ctypes.c_int,             # font_size
    ctypes.c_int,             # cursor_shape
    ctypes.c_int,             # blink_cursor
    ctypes.c_int,             # history_mode
    ctypes.c_int,             # history_size
    ctypes.c_int,             # scrollbar_pos
    ctypes.c_int,             # cursor_r
    ctypes.c_int,             # cursor_g
    ctypes.c_int,             # cursor_b
    ctypes.c_int,             # use_custom_cursor
]
_lib.qtermwidget_apply_profile.restype = None

# int qtermwidget_get_font_size(void*)
_lib.qtermwidget_get_font_size.argtypes = [ctypes.c_void_p]
_lib.qtermwidget_get_font_size.restype = ctypes.c_int

# void qtermwidget_set_font_size(void*, int)
_lib.qtermwidget_set_font_size.argtypes = [ctypes.c_void_p, ctypes.c_int]
_lib.qtermwidget_set_font_size.restype = None

# void qtermwidget_copy_selection(void*)
_lib.qtermwidget_copy_selection.argtypes = [ctypes.c_void_p]
_lib.qtermwidget_copy_selection.restype = None

# void qtermwidget_paste_clipboard(void*)
_lib.qtermwidget_paste_clipboard.argtypes = [ctypes.c_void_p]
_lib.qtermwidget_paste_clipboard.restype = None

# const char* qtermwidget_working_dir(void*)
_lib.qtermwidget_working_dir.argtypes = [ctypes.c_void_p]
_lib.qtermwidget_working_dir.restype = ctypes.c_char_p

# void qtermwidget_send_text(void* widget_ptr, const char* text)
_lib.qtermwidget_send_text.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
_lib.qtermwidget_send_text.restype = None

# void qtermwidget_destroy(void* widget_ptr)
_lib.qtermwidget_destroy.argtypes = [ctypes.c_void_p]
_lib.qtermwidget_destroy.restype = None


class KonsoleWidget(QtWidgets.QWidget):
    """A widget that embeds a native QTermWidget — Konsole's terminal engine.

    Loads the Konsole profile matching its name (default 'Garuda') and applies
    the color scheme, font, cursor shape, scrollbar position, and scrollback
    settings to QTermWidget via the C++ bridge.

    Full keyboard, mouse, copy/paste, and VT102 support.
    """

    # Konsole cursor_shape → bridge int
    _CURSOR_MAP = {"ibeam": 0, "underline": 1, "block": 2}
    # Konsole history_mode → bridge int
    _HISTORY_MAP = {"fixed": 0, "unlimited": 1, "none": 2}
    # Konsole scrollbar_pos → bridge int
    _SCROLLBAR_MAP = {"hidden": 0, "left": 1, "right": 2}

    def __init__(self, parent=None, profile_name: Optional[str] = None):
        super().__init__(parent)
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)

        self._term_raw_ptr = None
        self._term_wrapper = None
        self._profile = profile_loader.default_profile()
        self._profile_name = profile_name or "Garuda"

        # Load specific profile if requested
        loaded = profile_loader.load_profile(self._profile_name)
        if loaded:
            self._profile = loaded

        # Delay creation until we're shown (Wayland needs a window handle)
        self._pending_create = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._pending_create:
            self._pending_create = False
            self._create_terminal()

    @property
    def raw_ptr(self):
        return self._term_raw_ptr

    def copy(self):
        if self._term_raw_ptr:
            _lib.qtermwidget_copy_selection(self._term_raw_ptr)

    def paste(self):
        if self._term_raw_ptr:
            _lib.qtermwidget_paste_clipboard(self._term_raw_ptr)

    def zoom_in(self):
        if self._term_raw_ptr:
            sz = _lib.qtermwidget_get_font_size(self._term_raw_ptr)
            if sz < 36:
                _lib.qtermwidget_set_font_size(self._term_raw_ptr, sz + 2)

    def zoom_out(self):
        if self._term_raw_ptr:
            sz = _lib.qtermwidget_get_font_size(self._term_raw_ptr)
            if sz > 5:
                _lib.qtermwidget_set_font_size(self._term_raw_ptr, sz - 2)

    def working_dir(self) -> str:
        if self._term_raw_ptr:
            ptr = _lib.qtermwidget_working_dir(self._term_raw_ptr)
            if ptr:
                return ctypes.c_char_p(ptr).value.decode("utf-8", errors="replace")
        return os.getcwd()

    def _create_terminal(self):
        if self._term_raw_ptr is not None:
            return

        # Get our native C++ pointer via shiboken6
        try:
            import shiboken6
            self_ptr = shiboken6.getCppPointer(self)[0]
        except (ImportError, IndexError):
            self_ptr = int(self)

        # Create QTermWidget as child
        self._term_raw_ptr = _lib.qtermwidget_create(ctypes.c_void_p(self_ptr), 1)
        if not self._term_raw_ptr:
            raise RuntimeError("qtermwidget_create returned null — cannot create Konsole terminal")

        # Apply profile settings
        self._apply_profile()

        # Wrap the C++ pointer back into a PySide6 QWidget
        try:
            import shiboken6
            self._term_wrapper = shiboken6.wrapInstance(
                int(self._term_raw_ptr),
                QtWidgets.QWidget
            )
            # Add to our layout so it fills the space
            self.layout().addWidget(self._term_wrapper)
            self._term_wrapper.setFocus()
        except Exception as e:
            # Fallback: use findChild approach
            QtCore.QTimer.singleShot(50, self._find_term_child)

    def _apply_profile(self):
        """Apply the loaded profile settings to the QTermWidget via the bridge."""
        p = self._profile
        if not p or not self._term_raw_ptr:
            return

        color_scheme = p.get("color_scheme", "Sweet").encode("utf-8")
        font_family = p.get("font_family", "FiraCode Nerd Font Mono").encode("utf-8")
        font_size = p.get("font_size", 12)

        cursor_shape = self._CURSOR_MAP.get(p.get("cursor_shape", "block"), 2)
        blink_cursor = 1 if p.get("blink_cursor", True) else 0

        history_mode = self._HISTORY_MAP.get(p.get("history_mode", "unlimited"), 1)
        history_size = p.get("history_size", 1000000)

        scrollbar_pos = self._SCROLLBAR_MAP.get(p.get("scrollbar_pos", "right"), 2)

        cursor_r = p.get("cursor_color_r", 255)
        cursor_g = p.get("cursor_color_g", 0)
        cursor_b = p.get("cursor_color_b", 0)
        use_custom = 1 if "cursor_color_r" in p else 0

        _lib.qtermwidget_apply_profile(
            self._term_raw_ptr,
            color_scheme, font_family, font_size,
            cursor_shape, blink_cursor,
            history_mode, history_size,
            scrollbar_pos,
            cursor_r, cursor_g, cursor_b, use_custom,
        )

    def _find_term_child(self):
        """Fallback: find the QTermWidget child and set it up."""
        if self._term_wrapper:
            return
        for child in self.children():
            mo = child.metaObject()
            if mo and "QTermWidget" in mo.className():
                self._term_wrapper = child
                child.setParent(self)
                self.layout().addWidget(child)
                child.setGeometry(self.rect())
                child.show()
                child.setFocus()
                break

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._term_wrapper:
            self._term_wrapper.setGeometry(self.rect())

    def send_text(self, text: str):
        if self._term_raw_ptr:
            _lib.qtermwidget_send_text(self._term_raw_ptr, text.encode("utf-8"))

    def __del__(self):
        if self._term_raw_ptr:
            try:
                _lib.qtermwidget_destroy(self._term_raw_ptr)
            except Exception:
                pass
