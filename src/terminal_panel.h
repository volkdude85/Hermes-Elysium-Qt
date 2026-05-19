#ifndef HERMES_TERMINAL_PANEL_H
#define HERMES_TERMINAL_PANEL_H

/* TerminalPanel — real KonsolePart embedding via KParts.
 *
 * Each tab hosts a live konsolepart.so instance loaded through
 * KParts::PartLoader.  This gives us real Konsole sessions so
 * drag/drop from standalone Konsole moves the actual session
 * (not replayed text) into our window.
 *
 * Python ABI stays identical — no Python changes required.
 */

#include <QWidget>
#include <QMenuBar>
#include <QTabBar>
#include <QStackedWidget>
#include <QTimer>
#include <QPoint>
#include <QString>
#include <QVector>
#include <QShortcut>

/* Forward — KParts headers pulled in .cpp to keep build fast */
namespace KParts { class ReadOnlyPart; class Part; }

class TerminalPanel : public QWidget {
    Q_OBJECT

public:
    explicit TerminalPanel(QWidget *parent = nullptr);
    ~TerminalPanel() override;

    /* ── Tab management ─────────────────────────────────────────────── */

    int  addTab(const QString &shell = "bash", const QString &cwd = QString());
    void closeTab(int idx);
    void closeCurrentTab();
    void closeOtherTabs(int keepIdx);
    void duplicateTab(int idx);
    int  currentTabIndex() const;

    /* ── Konsole tab import (D-Bus session list for menu) ─────────────── */

    bool konsoleAvailable() const;
    QStringList konsoleSessions() const;
    QString      konsoleSessionTitle(const QString &sessionPath) const;
    int          konsoleSessionPid(const QString &sessionPath) const;
    QString      konsoleSessionCwd(const QString &sessionPath) const;
    int          importKonsoleTab(const QString &sessionPath);

    /* ── Per-tab operations ───────────────────────────────────────────── */

    void copySelection(int tabIdx = -1);
    void pasteClipboard(int tabIdx = -1);
    void zoomIn(int tabIdx = -1);
    void zoomOut(int tabIdx = -1);
    void sendText(int tabIdx, const QString &text);
    QString workingDirectory(int tabIdx) const;
    QString tabText(int tabIdx) const;
    void    setTabText(int tabIdx, const QString &text);

    /* ── Session save/restore (uses cwd only; live sessions die) ─────── */

    QString saveState() const;
    bool    restoreState(const QString &json);
    bool    haveSavedState() const;

    /* ── Menu helpers ───────────────────────────────────────────────── */

    void showTabContextMenu(int tabIdx, const QPoint &globalPos);
    void tearOffTab(int tabIdx);
    void detachAllToNewWindow();
    void newWindow();
    void startTabRename(int tabIdx);
    void prevTab();
    void nextTab();

protected:
    bool eventFilter(QObject *obj, QEvent *event) override;

private slots:
    void onTabChanged(int idx);
    void onPollDrag();

private:
    void buildUI();
    void buildMenus();
    KParts::ReadOnlyPart *partAt(int idx) const;
    int  findTabByPart(const KParts::ReadOnlyPart *p) const;
    void setupPart(KParts::ReadOnlyPart *part, const QString &shell, const QString &cwd);

    QMenuBar      *m_menubar;
    QTabBar       *m_tabBar;
    QStackedWidget*m_partStack;
    QShortcut     *m_newTabShortcut;
    QShortcut     *m_newWindowShortcut;
    QShortcut     *m_prevTabShortcut;
    QShortcut     *m_nextTabShortcut;

    int     m_dragStartTab;
    QPoint  m_dragStartPos;
    QTimer *m_dragTimer;
    int     m_renameTabIdx;
};

/* ── C ABI — callable from Python via ctypes / shiboken6 ─────────────────── */

extern "C" {

void*  terminal_panel_create(void *parent_ptr);
void   terminal_panel_destroy(void *panel_ptr);

/* Tab management */
int    terminal_panel_add_tab(void *panel_ptr, const char *shell, const char *cwd);
void   terminal_panel_close_tab(void *panel_ptr, int idx);
void   terminal_panel_close_current_tab(void *panel_ptr);
int    terminal_panel_current_tab(void *panel_ptr);

/* Konsole import */
int    terminal_panel_konsole_available(void *panel_ptr);
int    terminal_panel_konsole_session_count(void *panel_ptr);
const char* terminal_panel_konsole_session(void *panel_ptr, int i);
int    terminal_panel_import_konsole(void *panel_ptr, const char *session_path);

/* Terminal ops */
void   terminal_panel_copy(void *panel_ptr, int tab_idx);
void   terminal_panel_paste(void *panel_ptr, int tab_idx);
void   terminal_panel_zoom_in(void *panel_ptr, int tab_idx);
void   terminal_panel_zoom_out(void *panel_ptr, int tab_idx);
void   terminal_panel_send_text(void *panel_ptr, int tab_idx, const char *text);
const char* terminal_panel_working_dir(void *panel_ptr, int tab_idx);
const char* terminal_panel_tab_text(void *panel_ptr, int tab_idx);
void   terminal_panel_set_tab_text(void *panel_ptr, int tab_idx, const char *text);

/* Session state */
const char* terminal_panel_save_state(void *panel_ptr);
int    terminal_panel_restore_state(void *panel_ptr, const char *json);
int    terminal_panel_have_saved_state(void *panel_ptr);

/* Menu actions */
void   terminal_panel_show_context_menu(void *panel_ptr, int tab_idx, int global_x, int global_y);
void   terminal_panel_tear_off(void *panel_ptr, int tab_idx);
void   terminal_panel_detach_all(void *panel_ptr);
void   terminal_panel_new_window(void *panel_ptr);
void   terminal_panel_rename_tab(void *panel_ptr, int tab_idx);
void   terminal_panel_prev_tab(void *panel_ptr);
void   terminal_panel_next_tab(void *panel_ptr);

} /* extern "C" */

#endif /* HERMES_TERMINAL_PANEL_H */
