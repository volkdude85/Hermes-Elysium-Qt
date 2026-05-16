"""Embedded terminal widget — pyte + ptyprocess, renders via QPainter.
Gives you a full real terminal (bash, vim, htop, whatever) inside the Qt panel.
No embedded kitty or qtermwidget needed — it IS a terminal emulator."""

import fcntl
import os
import signal
import struct
import termios

from PySide6 import QtCore, QtGui, QtWidgets

import pyte
import ptyprocess


class EmbeddedTerminal(QtWidgets.QWidget):
    """A proper VT102 terminal emulator widget using pyte + ptyprocess."""

    # Colors — Nord-inspired dark palette
    COLORS = {
        "bg": QtGui.QColor("#0d0d1a"),
        "fg": QtGui.QColor("#d8dee9"),
        "black": QtGui.QColor("#3b4252"),
        "red": QtGui.QColor("#bf616a"),
        "green": QtGui.QColor("#a3be8c"),
        "yellow": QtGui.QColor("#ebcb8b"),
        "blue": QtGui.QColor("#81a1c1"),
        "magenta": QtGui.QColor("#b48ead"),
        "cyan": QtGui.QColor("#88c0d0"),
        "white": QtGui.QColor("#e5e9f0"),
        "bright_black": QtGui.QColor("#4c566a"),
        "bright_red": QtGui.QColor("#bf616a"),
        "bright_green": QtGui.QColor("#a3be8c"),
        "bright_yellow": QtGui.QColor("#ebcb8b"),
        "bright_blue": QtGui.QColor("#81a1c1"),
        "bright_magenta": QtGui.QColor("#b48ead"),
        "bright_cyan": QtGui.QColor("#88c0d0"),
        "bright_white": QtGui.QColor("#8fbcbb"),
    }

    ANSI_COLORS = [
        "black", "red", "green", "yellow", "blue",
        "magenta", "cyan", "white",
        "bright_black", "bright_red", "bright_green", "bright_yellow",
        "bright_blue", "bright_magenta", "bright_cyan", "bright_white",
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumHeight(100)

        self._font = QtGui.QFont("JetBrains Mono", 10)
        self._fm = QtGui.QFontMetrics(self._font)
        self._char_w = self._fm.horizontalAdvance("W")
        self._char_h = self._fm.height()

        # pyte screen
        self._cols = 80
        self._rows = 24
        self._screen = pyte.Screen(self._cols, self._rows)
        self._stream = pyte.Stream(self._screen)

        # pty
        self._process = None
        self._notifier = None

        # Cursor blink
        self._cursor_visible = True
        self._cursor_timer = QtCore.QTimer(self)
        self._cursor_timer.timeout.connect(self._toggle_cursor)
        self._cursor_timer.start(500)

        # Scrollback buffer
        self._scrollback = []
        self._scroll_offset = 0

        self._spawn_shell()

    def resizeEvent(self, event):
        w = self.width() - 4
        h = self.height() - 4
        new_cols = max(20, w // self._char_w)
        new_rows = max(5, h // self._char_h)
        if new_cols != self._cols or new_rows != self._rows:
            self._cols = new_cols
            self._rows = new_rows
            self._screen.resize(new_rows, new_cols)
            self._resize_pty()

    def _spawn_shell(self):
        try:
            shell = os.environ.get("SHELL", "/bin/bash")
            self._process = ptyprocess.PtyProcess.spawn([shell])
            self._resize_pty()
            self._notifier = QtCore.QSocketNotifier(
                self._process.fd, QtCore.QSocketNotifier.ActivationType.Read, self
            )
            self._notifier.activated.connect(self._read_pty)
        except Exception as e:
            self._screen.display[0] = f"[term init error: {e}]"

    def _resize_pty(self):
        if self._process and self._process.isalive():
            try:
                self._process.setwinsize(self._rows, self._cols)
            except Exception:
                pass

    def _read_pty(self):
        try:
            data = os.read(self._process.fd, 4096)
            if not data:
                self._close()
                return
            decoded = data.decode("utf-8", errors="replace")
            self._stream.feed(decoded)
            self.update()
        except (OSError, EOFError):
            self._close()

    def _write_pty(self, data: str):
        if self._process and self._process.isalive():
            try:
                self._process.write(data.encode())
            except OSError:
                self._close()

    def _close(self):
        if self._notifier:
            self._notifier.setEnabled(False)
            self._notifier = None
        if self._process:
            try:
                self._process.close()
            except Exception:
                pass
            self._process = None
        self.update()

    def _toggle_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setFont(self._font)
        painter.fillRect(self.rect(), self.COLORS["bg"])

        cursor = self._screen.cursor
        cursor_x = cursor.x if cursor else 0
        cursor_y = cursor.y if cursor else 0

        for y in range(self._screen.lines):
            for x in range(self._screen.columns):
                char = self._screen.buffer[y][x]
                ch = char.data if char.data else " "
                fg = self._get_color(char.fg, char.bold)
                bg = self._get_bg(char.bg) if char.bg != "default" else None
                xp = 2 + x * self._char_w
                yp = 2 + y * self._char_h

                # Draw cursor
                is_cursor = (
                    self._cursor_visible
                    and y == cursor_y
                    and x == cursor_x
                    and self._process
                )
                if is_cursor:
                    painter.fillRect(xp, yp, self._char_w, self._char_h, QtGui.QColor("#e5e9f0"))
                    painter.setPen(self.COLORS["bg"])
                elif bg:
                    painter.fillRect(xp, yp, self._char_w, self._char_h, bg)
                    painter.setPen(fg)
                else:
                    painter.setPen(fg)

                painter.drawText(xp, yp, self._char_w, self._char_h, QtCore.Qt.AlignmentFlag.AlignLeft, ch)

        painter.end()

    def _get_color(self, color_spec, bold=False) -> QtGui.QColor:
        name = "fg"
        if color_spec and color_spec != "default":
            try:
                idx = int(color_spec) if isinstance(color_spec, str) else color_spec
                if 0 <= idx < 16:
                    if bold and idx < 8:
                        idx += 8
                    name = self.ANSI_COLORS[idx]
            except (ValueError, TypeError):
                pass
        return self.COLORS.get(name, self.COLORS["fg"])

    def _get_bg(self, color_spec) -> QtGui.QColor:
        if color_spec and color_spec != "default":
            try:
                idx = int(color_spec)
                if 0 <= idx < 8:
                    name = self.ANSI_COLORS[idx]
                    c = self.COLORS.get(name)
                    # Dim background slightly
                    if c:
                        return QtGui.QColor(
                            min(255, c.red() + 30),
                            min(255, c.green() + 30),
                            min(255, c.blue() + 30),
                        )
            except (ValueError, TypeError):
                pass
        return None

    def keyPressEvent(self, event):
        if not self._process or not self._process.isalive():
            return

        key = event.key()
        text = event.text()

        # Special key mappings
        if key == QtCore.Qt.Key.Key_Return:
            self._write_pty("\r")
        elif key == QtCore.Qt.Key.Key_Backspace:
            self._write_pty("\x7f")
        elif key == QtCore.Qt.Key.Key_Tab:
            self._write_pty("\t")
        elif key == QtCore.Qt.Key.Key_Escape:
            self._write_pty("\x1b")
        elif key == QtCore.Qt.Key.Key_Up:
            self._write_pty("\x1b[A")
        elif key == QtCore.Qt.Key.Key_Down:
            self._write_pty("\x1b[B")
        elif key == QtCore.Qt.Key.Key_Right:
            self._write_pty("\x1b[C")
        elif key == QtCore.Qt.Key.Key_Left:
            self._write_pty("\x1b[D")
        elif key == QtCore.Qt.Key.Key_Home:
            self._write_pty("\x1b[H")
        elif key == QtCore.Qt.Key.Key_End:
            self._write_pty("\x1b[F")
        elif key == QtCore.Qt.Key.Key_PageUp:
            self._write_pty("\x1b[5~")
        elif key == QtCore.Qt.Key.Key_PageDown:
            self._write_pty("\x1b[6~")
        elif key == QtCore.Qt.Key.Key_Delete:
            self._write_pty("\x1b[3~")
        elif text:
            # Ctrl+C, Ctrl+D, etc.
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                if key == QtCore.Qt.Key.Key_C:
                    self._write_pty("\x03")
                elif key == QtCore.Qt.Key.Key_D:
                    self._write_pty("\x04")
                elif key == QtCore.Qt.Key.Key_Z:
                    self._write_pty("\x1a")
                elif key == QtCore.Qt.Key.Key_L:
                    self._write_pty("\x0c")
                elif key == QtCore.Qt.Key.Key_A:
                    self._write_pty("\x01")
                elif key == QtCore.Qt.Key.Key_U:
                    self._write_pty("\x15")
                else:
                    self._write_pty(text)
            elif key == QtCore.Qt.Key.Key_Shift and event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier:
                pass  # Shift by itself
            else:
                self._write_pty(text)

    def focusInEvent(self, event):
        self._cursor_visible = True
        self._cursor_timer.start(500)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._cursor_visible = False
        self._cursor_timer.stop()
        self.update()
        super().focusOutEvent(event)

    def copy_selection(self):
        """Copy current visible text to clipboard."""
        lines = ["".join(cell.data for cell in row) for row in self._screen.buffer]
        text = "\n".join(line.rstrip() for line in lines).strip()
        if text:
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(text)

    def paste_clipboard(self):
        clipboard = QtWidgets.QApplication.clipboard()
        text = clipboard.text()
        if text:
            self._write_pty(text)
