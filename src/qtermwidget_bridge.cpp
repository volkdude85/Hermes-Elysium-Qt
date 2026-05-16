/* QTermWidget bridge — exposes QTermWidget as a QWidget* via C ABI
   so PySide6 can wrap it and parent it into our Qt app.
   Uses libqtermwidget6 — the same terminal engine Konsole runs on. */
#include <QWidget>
#include <QFont>
#include <QColor>
#include <qtermwidget6/qtermwidget.h>

extern "C" {

void* qtermwidget_create(void* parent_ptr, int start_shell) {
    QWidget* parent = static_cast<QWidget*>(parent_ptr);
    QTermWidget* w = new QTermWidget(start_shell, parent);
    w->setFocusPolicy(Qt::StrongFocus);
    w->setScrollBarPosition(QTermWidget::ScrollBarRight);
    w->setTerminalOpacity(1.0);
    w->setTerminalFont(QFont("FiraCode Nerd Font Mono", 12));
    w->setKeyboardCursorShape(QTermWidget::KeyboardCursorShape::BlockCursor);
    w->setBlinkingCursor(true);
    w->setMargin(0);
    w->setTerminalSizeHint(false);
    w->setKeyBindings(QString());
    return static_cast<void*>(w);
}

void qtermwidget_apply_profile(void* widget_ptr, const char* color_scheme,
    const char* font_family, int font_size,
    int cursor_shape,              /* 0=ibeam, 1=underline, 2=block */
    int blink_cursor,
    int history_mode,              /* 0=fixed, 1=unlimited, 2=none */
    int history_size,
    int scrollbar_pos,             /* 0=hidden, 1=left, 2=right */
    int cursor_r, int cursor_g, int cursor_b, int use_custom_cursor) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    if (!w) return;

    /* Color scheme — add system konsole dir so it finds Sweet etc. */
    w->addCustomColorSchemeDir(QString("/usr/share/konsole"));
    if (color_scheme && *color_scheme) {
        w->setColorScheme(QString::fromUtf8(color_scheme));
    }

    /* Font */
    if (font_family && *font_family && font_size > 0) {
        w->setTerminalFont(QFont(QString::fromUtf8(font_family), font_size));
    }

    /* Cursor shape */
    switch (cursor_shape) {
        case 0: w->setKeyboardCursorShape(QTermWidget::KeyboardCursorShape::IBeamCursor); break;
        case 1: w->setKeyboardCursorShape(QTermWidget::KeyboardCursorShape::UnderlineCursor); break;
        default: w->setKeyboardCursorShape(QTermWidget::KeyboardCursorShape::BlockCursor); break;
    }
    w->setBlinkingCursor(blink_cursor != 0);

    /* Custom cursor color — skip if unavailable in this version of libqtermwidget6 */
    (void)cursor_r; (void)cursor_g; (void)cursor_b; (void)use_custom_cursor;

    /* Scrollbar position */
    switch (scrollbar_pos) {
        case 0: w->setScrollBarPosition(QTermWidget::ScrollBarPosition::NoScrollBar); break;
        case 1: w->setScrollBarPosition(QTermWidget::ScrollBarPosition::ScrollBarLeft); break;
        default: w->setScrollBarPosition(QTermWidget::ScrollBarPosition::ScrollBarRight); break;
    }

    /* History (scrollback) — Konsole's HistoryMode */
    switch (history_mode) {
        case 0: /* fixed line count */
            w->setHistorySize(history_size > 0 ? history_size : 1000);
            break;
        case 1: /* unlimited */
            w->setHistorySize(1000000);
            break;
        case 2: /* no scrollback */
            w->setHistorySize(0);
            break;
        default:
            w->setHistorySize(1000000);
            break;
    }
}

/* ── Font size zoom ─────────────────────────────────────────────────────── */

int qtermwidget_get_font_size(void* widget_ptr) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    if (!w) return 12;
    return w->getTerminalFont().pointSize();
}

void qtermwidget_set_font_size(void* widget_ptr, int size) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    if (!w || size < 5 || size > 72) return;
    QFont f = w->getTerminalFont();
    f.setPointSize(size);
    w->setTerminalFont(f);
}

/* ── Selection / clipboard ──────────────────────────────────────────────── */

void qtermwidget_copy_selection(void* widget_ptr) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    if (!w) return;
    w->copyClipboard();
}

void qtermwidget_paste_clipboard(void* widget_ptr) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    if (!w) return;
    w->pasteClipboard();
}

/* ── Working directory ──────────────────────────────────────────────────── */

const char* qtermwidget_working_dir(void* widget_ptr) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    if (!w) return nullptr;
    static QByteArray cached;
    cached = w->workingDirectory().toUtf8();
    return cached.constData();
}

/* ── Text I/O ───────────────────────────────────────────────────────────── */

void qtermwidget_send_text(void* widget_ptr, const char* text) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    w->sendText(QString::fromUtf8(text));
}

void qtermwidget_destroy(void* widget_ptr) {
    QTermWidget* w = static_cast<QTermWidget*>(widget_ptr);
    delete w;
}

}
