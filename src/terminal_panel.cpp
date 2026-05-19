#include "terminal_panel.h"
#include <QApplication>
#include <QInputDialog>
#include <QMessageBox>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTimer>
#include <QCursor>
#include <QMouseEvent>
#include <QKeyEvent>
#include <QProcess>
#include <QDBusInterface>
#include <QDBusReply>
#include <QMainWindow>
#include <QVBoxLayout>
#include <QLineEdit>

TerminalPanel::TerminalPanel(QWidget *parent)
    : QWidget(parent)
    , m_menubar(nullptr)
    , m_tabBar(nullptr)
    , m_termStack(nullptr)
    , m_newTabShortcut(nullptr)
    , m_newWindowShortcut(nullptr)
    , m_prevTabShortcut(nullptr)
    , m_nextTabShortcut(nullptr)
    , m_dragStartTab(-1)
    , m_dragTimer(nullptr)
    , m_renameTabIdx(-1)
{
    buildUI();
    buildMenus();

    // Shortcuts that work even when terminal has focus
    m_newTabShortcut = new QShortcut(QKeySequence("Ctrl+Shift+T"), this);
    connect(m_newTabShortcut, &QShortcut::activated, this, [this]() { addTab("bash"); });

    m_newWindowShortcut = new QShortcut(QKeySequence("Ctrl+Shift+N"), this);
    connect(m_newWindowShortcut, &QShortcut::activated, this, &TerminalPanel::newWindow);

    m_prevTabShortcut = new QShortcut(QKeySequence("Ctrl+Shift+,"), this);
    connect(m_prevTabShortcut, &QShortcut::activated, this, &TerminalPanel::prevTab);

    m_nextTabShortcut = new QShortcut(QKeySequence("Ctrl+Shift+."), this);
    connect(m_nextTabShortcut, &QShortcut::activated, this, &TerminalPanel::nextTab);

    // Drag timer
    m_dragTimer = new QTimer(this);
    m_dragTimer->setInterval(100);
    connect(m_dragTimer, &QTimer::timeout, this, &TerminalPanel::onPollDrag);

    // Start with one tab
    addTab("bash");

    // Restore state after event loop
    QTimer::singleShot(100, [this]() {
        // Optional: restore from ~/.hermes/elysium_terminal_state.json
    });
}

TerminalPanel::~TerminalPanel() {}

void TerminalPanel::buildUI()
{
    setLayout(new QVBoxLayout());
    layout()->setContentsMargins(0, 0, 0, 0);
    layout()->setSpacing(0);

    // Menu bar
    m_menubar = new QMenuBar(this);
    m_menubar->setStyleSheet(
        "QMenuBar { background: #1e1e1e; color: #e0e0e0; padding: 1px 0; font-size: 12px; }"
        "QMenuBar::item { padding: 4px 8px; } QMenuBar::item:selected { background: #2d2d2d; }"
        "QMenu { background: #1e1e1e; color: #e0e0e0; border: 1px solid #333; }");
    layout()->addWidget(m_menubar);

    // Tab bar
    m_tabBar = new QTabBar(this);
    m_tabBar->setTabsClosable(true);
    m_tabBar->setMovable(true);
    m_tabBar->setExpanding(false);
    m_tabBar->setStyleSheet(
        "QTabBar { background: #1e1e1e; padding: 0; }"
        "QTabBar::tab { background: #252525; color: #ccc; padding: 4px 16px; border: none; font-size: 11px; }"
        "QTabBar::tab:selected { background: #333; color: #fff; border-bottom: 2px solid #e74c3c; }"
        "QTabBar::tab:hover { background: #2a2a2a; }");
    connect(m_tabBar, &QTabBar::currentChanged, this, &TerminalPanel::onTabChanged);
    connect(m_tabBar, &QTabBar::tabCloseRequested, this, &TerminalPanel::closeTab);
    m_tabBar->installEventFilter(this);
    installEventFilter(this);
    layout()->addWidget(m_tabBar);

    // Stacked widget for terminals
    m_termStack = new QStackedWidget(this);
    m_termStack->setStyleSheet("background: #0a0a18;");
    layout()->addWidget(m_termStack);
}

void TerminalPanel::buildMenus()
{
    // File menu
    auto *fileMenu = m_menubar->addMenu("File");
    fileMenu->addAction("New Tab", [this]() { addTab("bash"); });
    fileMenu->addAction("New Window", this, &TerminalPanel::newWindow);
    fileMenu->addSeparator();
    fileMenu->addAction("Import Tab from Konsole…", [this]() {
        if (!konsoleAvailable()) {
            QMessageBox::information(this, "Import Tab", "Konsole not running or unreachable via D-Bus.");
            return;
        }
        QStringList sessions = konsoleSessions();
        if (sessions.isEmpty()) {
            QMessageBox::information(this, "Import Tab", "No Konsole sessions found.");
            return;
        }
        QStringList labels;
        QVector<QString> cwds;
        for (const auto &sp : sessions) {
            QString title = konsoleSessionTitle(sp);
            int pid = konsoleSessionPid(sp);
            QString cwd = konsoleSessionCwd(sp);
            QString label = QString("#%1: %2").arg(sp.section('/', -1)).arg(title.isEmpty() ? "shell" : title);
            if (!cwd.isEmpty()) {
                QString home = QDir::homePath();
                QString shortCwd = cwd;
                if (shortCwd.startsWith(home)) shortCwd.replace(0, home.length(), "~");
                label += QString("  (%1)").arg(shortCwd);
            }
            labels << label;
            cwds << cwd;
        }
        bool ok;
        QString chosen = QInputDialog::getItem(this, "Import Tab from Konsole",
            "Select a Konsole session tab:", labels, 0, false, &ok);
        if (!ok) return;
        int idx = labels.indexOf(chosen);
        if (idx < 0) return;
        importKonsoleTab(sessions[idx]);
    });
    fileMenu->addSeparator();
    fileMenu->addAction("Close Tab", QKeySequence("Ctrl+W"), this, &TerminalPanel::closeCurrentTab);
    fileMenu->addAction("Quit", QKeySequence("Ctrl+Q"), qApp, &QApplication::quit);

    // Edit menu
    auto *editMenu = m_menubar->addMenu("Edit");
    editMenu->addAction("Copy", QKeySequence("Ctrl+Shift+C"), this, [this]() { copySelection(); });
    editMenu->addAction("Paste", QKeySequence("Ctrl+Shift+V"), this, [this]() { pasteClipboard(); });
    editMenu->addSeparator();
    editMenu->addAction("Select All");

    // View menu
    auto *viewMenu = m_menubar->addMenu("View");
    viewMenu->addAction("Increase Font Size", QKeySequence("Ctrl++"), this, [this]() { zoomIn(); });
    viewMenu->addAction("Decrease Font Size", QKeySequence("Ctrl+-"), this, [this]() { zoomOut(); });
    viewMenu->addSeparator();
    viewMenu->addAction("Show Menu Bar", QKeySequence("Ctrl+Shift+M"), this, [this]() {
        m_menubar->setVisible(!m_menubar->isVisible());
    });

    // Bookmarks (stub)
    m_menubar->addMenu("Bookmarks");

    // Settings (stub for now)
    m_menubar->addMenu("Settings");

    // Help
    auto *helpMenu = m_menubar->addMenu("Help");
    helpMenu->addAction("Konsole Handbook");
    helpMenu->addAction("Report Bug…");
    helpMenu->addAction("About Konsole");
}

QTermWidget *TerminalPanel::terminalAt(int idx) const
{
    if (idx < 0 || idx >= m_termStack->count()) return nullptr;
    QWidget *container = m_termStack->widget(idx);
    if (!container) return nullptr;
    return container->findChild<QTermWidget *>();
}

int TerminalPanel::findTabByWidget(const QTermWidget *w) const
{
    for (int i = 0; i < m_termStack->count(); ++i) {
        if (terminalAt(i) == w) return i;
    }
    return -1;
}

int TerminalPanel::addTab(const QString &shell, const QString &cwd)
{
    QWidget *container = new QWidget();
    container->setLayout(new QVBoxLayout());
    container->layout()->setContentsMargins(0, 0, 0, 0);

    QTermWidget *term = new QTermWidget(0, container);
    term->setShellProgram(shell);
    if (!cwd.isEmpty()) term->setWorkingDirectory(cwd);
    term->startShellProgram();
    term->setColorScheme("Sweet");
    term->setTerminalFont(QFont("FiraCode Nerd Font", 11));

    container->layout()->addWidget(term);
    m_termStack->addWidget(container);

    int idx = m_tabBar->addTab(QString(":%1 %2").arg(shell).arg(cwd.isEmpty() ? "" : cwd));
    m_tabBar->setCurrentIndex(idx);
    m_termStack->setCurrentWidget(container);

    // Update tab text with CWD once ready
    connect(term, &QTermWidget::currentDirectoryChanged, this, [this, term]() {
        int i = findTabByWidget(term);
        if (i >= 0) {
            QString dir = term->workingDirectory();
            if (!dir.isEmpty()) m_tabBar->setTabText(i, QString("~ %1").arg(QDir(dir).dirName()));
        }
    });

    return idx;
}

void TerminalPanel::closeTab(int idx)
{
    if (m_tabBar->count() <= 1) return;
    QWidget *w = m_termStack->widget(idx);
    m_termStack->removeWidget(w);
    w->deleteLater();
    m_tabBar->removeTab(idx);
}

void TerminalPanel::closeCurrentTab()
{
    closeTab(m_tabBar->currentIndex());
}

void TerminalPanel::closeOtherTabs(int keepIdx)
{
    for (int i = m_tabBar->count() - 1; i >= 0; --i) {
        if (i != keepIdx) closeTab(i);
    }
}

void TerminalPanel::duplicateTab(int idx)
{
    QTermWidget *src = terminalAt(idx);
    QString cwd = src ? src->workingDirectory() : QString();
    addTab("bash", cwd);
}

bool TerminalPanel::konsoleAvailable() const
{
    QDBusInterface iface("org.kde.konsole", "/Konsole", "org.kde.konsole.Window", QDBusConnection::sessionBus());
    return iface.isValid();
}

QStringList TerminalPanel::konsoleSessions() const
{
    QStringList result;
    QDBusInterface iface("org.kde.konsole", "/Konsole", "org.kde.konsole.Window", QDBusConnection::sessionBus());
    if (!iface.isValid()) return result;
    QDBusReply<QStringList> reply = iface.call("listAvailableSessions");
    if (reply.isValid()) result = reply.value();
    return result;
}

QString TerminalPanel::konsoleSessionTitle(const QString &sessionPath) const
{
    QDBusInterface iface("org.kde.konsole", sessionPath, "org.kde.konsole.Session", QDBusConnection::sessionBus());
    if (!iface.isValid()) return QString();
    QDBusReply<QString> reply = iface.call("title", 1);
    return reply.isValid() ? reply.value() : QString();
}

int TerminalPanel::konsoleSessionPid(const QString &sessionPath) const
{
    QDBusInterface iface("org.kde.konsole", sessionPath, "org.kde.konsole.Session", QDBusConnection::sessionBus());
    if (!iface.isValid()) return -1;
    QDBusReply<int> reply = iface.call("foregroundProcessId");
    return reply.isValid() ? reply.value() : -1;
}

QString TerminalPanel::konsoleSessionCwd(const QString &sessionPath) const
{
    int pid = konsoleSessionPid(sessionPath);
    if (pid <= 0) return QString();
    QFile f(QString("/proc/%1/cwd").arg(pid));
    if (!f.exists()) return QString();
    return f.symLinkTarget();
}

QString TerminalPanel::konsoleSessionScrollback(const QString &sessionPath) const
{
    QDBusInterface iface("org.kde.konsole", sessionPath, "org.kde.konsole.Session", QDBusConnection::sessionBus());
    if (!iface.isValid()) return QString();
    QDBusReply<QString> reply = iface.call("getAllDisplayedText");
    return reply.isValid() ? reply.value() : QString();
}

int TerminalPanel::importKonsoleTab(const QString &sessionPath)
{
    QString cwd = konsoleSessionCwd(sessionPath);
    QString scrollback = konsoleSessionScrollback(sessionPath);
    int newIdx = addTab("bash", cwd);
    if (!scrollback.isEmpty()) {
        QTimer::singleShot(400, [this, newIdx, scrollback]() {
            replayScrollback(newIdx, scrollback);
        });
    }
    return newIdx;
}

void TerminalPanel::replayScrollback(int tabIdx, const QString &content)
{
    QTermWidget *term = terminalAt(tabIdx);
    if (!term) return;
    QStringList lines = content.split('\n');
    QStringList cmds;
    for (const QString &line : lines) {
        if (line.trimmed().isEmpty()) {
            cmds << "printf '\\n'";
        } else {
            cmds << QString("printf '%%s\\n' %1").arg(QProcess::splitCommand(line).join(" "));
        }
    }
    term->sendText(cmds.join("; ") + "\n");
}

void TerminalPanel::copySelection(int tabIdx)
{
    QTermWidget *term = (tabIdx >= 0) ? terminalAt(tabIdx) : terminalAt(m_tabBar->currentIndex());
    if (term) term->copyClipboard();
}

void TerminalPanel::pasteClipboard(int tabIdx)
{
    QTermWidget *term = (tabIdx >= 0) ? terminalAt(tabIdx) : terminalAt(m_tabBar->currentIndex());
    if (term) term->pasteClipboard();
}

void TerminalPanel::zoomIn(int tabIdx)
{
    QTermWidget *term = (tabIdx >= 0) ? terminalAt(tabIdx) : terminalAt(m_tabBar->currentIndex());
    if (term) term->zoomIn();
}

void TerminalPanel::zoomOut(int tabIdx)
{
    QTermWidget *term = (tabIdx >= 0) ? terminalAt(tabIdx) : terminalAt(m_tabBar->currentIndex());
    if (term) term->zoomOut();
}

void TerminalPanel::sendText(int tabIdx, const QString &text)
{
    QTermWidget *term = terminalAt(tabIdx);
    if (term) term->sendText(text);
}

QString TerminalPanel::workingDirectory(int tabIdx) const
{
    QTermWidget *term = terminalAt(tabIdx);
    return term ? term->workingDirectory() : QString();
}

QString TerminalPanel::tabText(int tabIdx) const
{
    return m_tabBar->tabText(tabIdx);
}

void TerminalPanel::setTabText(int tabIdx, const QString &text)
{
    m_tabBar->setTabText(tabIdx, text);
}

QString TerminalPanel::saveState() const
{
    QJsonArray arr;
    for (int i = 0; i < m_tabBar->count(); ++i) {
        QJsonObject obj;
        obj["name"] = m_tabBar->tabText(i);
        obj["cwd"] = workingDirectory(i);
        arr.append(obj);
    }
    QJsonDocument doc(arr);
    return doc.toJson(QJsonDocument::Compact);
}

bool TerminalPanel::restoreState(const QString &json)
{
    QJsonParseError err;
    QJsonDocument doc = QJsonDocument::fromJson(json.toUtf8(), &err);
    if (err.error != QJsonParseError::NoError) return false;

    QJsonArray arr = doc.array();
    while (m_tabBar->count() > 0) closeTab(0);
    for (const QJsonValue &v : arr) {
        QJsonObject o = v.toObject();
        QString cwd = o["cwd"].toString();
        addTab("bash", cwd);
    }
    return true;
}

bool TerminalPanel::haveSavedState() const
{
    return QFile::exists(QDir::homePath() + "/.hermes/elysium_terminal_state.json");
}

void TerminalPanel::showTabContextMenu(int tabIdx, const QPoint &globalPos)
{
    QMenu menu(this);
    menu.addAction("Duplicate Tab", [this, tabIdx]() { duplicateTab(tabIdx); });
    menu.addAction("Detach Tab", [this, tabIdx]() { tearOffTab(tabIdx); });
    menu.addSeparator();
    menu.addAction("Import Tab from Konsole…", [this]() { /* trigger import */ });
    menu.addSeparator();
    menu.addAction("Rename Tab", [this, tabIdx]() { startTabRename(tabIdx); });
    menu.addSeparator();
    menu.addAction("Close Tab", [this, tabIdx]() { closeTab(tabIdx); });
    menu.addAction("Close Other Tabs", [this, tabIdx]() { closeOtherTabs(tabIdx); });
    menu.exec(globalPos);
}

void TerminalPanel::tearOffTab(int tabIdx)
{
    QWidget *w = m_termStack->widget(tabIdx);
    m_termStack->removeWidget(w);
    QString txt = m_tabBar->tabText(tabIdx);
    m_tabBar->removeTab(tabIdx);

    QMainWindow *win = new QMainWindow();
    win->setWindowTitle(txt + " — Hermes Elysium");
    win->setAttribute(Qt::WA_DeleteOnClose);
    win->setCentralWidget(w);
    win->resize(900, 600);
    win->show();

    if (m_tabBar->count() == 0) addTab("bash");
}

void TerminalPanel::detachAllToNewWindow()
{
    QMainWindow *win = new QMainWindow();
    win->setWindowTitle("Terminal — Hermes Elysium");
    win->setAttribute(Qt::WA_DeleteOnClose);

    QWidget *container = new QWidget();
    QVBoxLayout *lay = new QVBoxLayout(container);
    lay->setContentsMargins(0,0,0,0);

    QTabBar *newBar = new QTabBar();
    newBar->setTabsClosable(true);
    newBar->setMovable(true);
    QStackedWidget *newStack = new QStackedWidget();

    while (m_tabBar->count() > 0) {
        QWidget *w = m_termStack->widget(0);
        m_termStack->removeWidget(w);
        QString t = m_tabBar->tabText(0);
        m_tabBar->removeTab(0);
        newBar->addTab(t);
        newStack->addWidget(w);
    }
    connect(newBar, &QTabBar::currentChanged, newStack, &QStackedWidget::setCurrentIndex);
    lay->addWidget(newBar);
    lay->addWidget(newStack, 1);
    win->setCentralWidget(container);
    win->resize(900, 650);
    win->show();
}

void TerminalPanel::newWindow()
{
    QProcess::startDetached("konsole");
}

void TerminalPanel::startTabRename(int tabIdx)
{
    QRect rect = m_tabBar->tabRect(tabIdx);
    QLineEdit *editor = new QLineEdit(m_tabBar);
    editor->setText(m_tabBar->tabText(tabIdx));
    editor->selectAll();
    editor->setFixedWidth(rect.width());
    editor->move(rect.topLeft());
    editor->show();
    editor->setFocus();

    connect(editor, &QLineEdit::editingFinished, this, [this, editor, tabIdx]() {
        QString newName = editor->text().trimmed();
        if (!newName.isEmpty()) m_tabBar->setTabText(tabIdx, newName);
        editor->deleteLater();
    });
}

void TerminalPanel::prevTab()
{
    int idx = m_tabBar->currentIndex();
    if (idx > 0) m_tabBar->setCurrentIndex(idx - 1);
}

void TerminalPanel::nextTab()
{
    int idx = m_tabBar->currentIndex();
    if (idx < m_tabBar->count() - 1) m_tabBar->setCurrentIndex(idx + 1);
}

bool TerminalPanel::eventFilter(QObject *obj, QEvent *event)
{
    if (obj == m_tabBar) {
        if (event->type() == QEvent::MouseButtonDblClick) {
            QMouseEvent *me = static_cast<QMouseEvent*>(event);
            int idx = m_tabBar->tabAt(me->pos());
            if (idx == -1) {
                addTab("bash");
                return true;
            }
            startTabRename(idx);
            return true;
        }
        if (event->type() == QEvent::MouseButtonPress) {
            QMouseEvent *me = static_cast<QMouseEvent*>(event);
            if (me->button() == Qt::MiddleButton) {
                int idx = m_tabBar->tabAt(me->pos());
                if (idx >= 0) { closeTab(idx); return true; }
            } else if (me->button() == Qt::LeftButton) {
                m_dragStartTab = m_tabBar->tabAt(me->pos());
                if (m_dragStartTab >= 0) {
                    m_dragStartPos = me->globalPosition().toPoint();
                    m_dragTimer->start();
                }
            } else if (me->button() == Qt::RightButton) {
                int idx = m_tabBar->tabAt(me->pos());
                if (idx >= 0) {
                    showTabContextMenu(idx, me->globalPosition().toPoint());
                    return true;
                }
            }
        }
        if (event->type() == QEvent::MouseButtonRelease) {
            m_dragStartTab = -1;
            m_dragTimer->stop();
        }
    }
    return QWidget::eventFilter(obj, event);
}

void TerminalPanel::onTabChanged(int idx)
{
    m_termStack->setCurrentIndex(idx);
}

void TerminalPanel::onPollDrag()
{
    if (m_dragStartTab < 0) {
        m_dragTimer->stop();
        return;
    }
    QPoint pos = QCursor::pos();
    int dist = (pos - m_dragStartPos).manhattanLength();
    if (dist > 90 && m_tabBar->count() > 1) {
        int idx = m_dragStartTab;
        m_dragStartTab = -1;
        m_dragTimer->stop();
        tearOffTab(idx);
    }
}

// ─────────────────────────────────────────────────────────────────
// C ABI Implementation
// ─────────────────────────────────────────────────────────────────

extern "C" {

void* terminal_panel_create(void *parent_ptr) {
    QWidget *parent = static_cast<QWidget*>(parent_ptr);
    return new TerminalPanel(parent);
}

void terminal_panel_destroy(void *panel_ptr) {
    delete static_cast<TerminalPanel*>(panel_ptr);
}

int terminal_panel_add_tab(void *panel_ptr, const char *shell, const char *cwd) {
    TerminalPanel *p = static_cast<TerminalPanel*>(panel_ptr);
    return p->addTab(QString(shell ? shell : "bash"), QString(cwd ? cwd : ""));
}

void terminal_panel_close_tab(void *panel_ptr, int idx) {
    static_cast<TerminalPanel*>(panel_ptr)->closeTab(idx);
}

void terminal_panel_close_current_tab(void *panel_ptr) {
    static_cast<TerminalPanel*>(panel_ptr)->closeCurrentTab();
}

int terminal_panel_current_tab(void *panel_ptr) {
    return static_cast<TerminalPanel*>(panel_ptr)->currentTabIndex();
}

int terminal_panel_konsole_available(void *panel_ptr) {
    return static_cast<TerminalPanel*>(panel_ptr)->konsoleAvailable() ? 1 : 0;
}

int terminal_panel_konsole_session_count(void *panel_ptr) {
    return static_cast<TerminalPanel*>(panel_ptr)->konsoleSessions().size();
}

const char* terminal_panel_konsole_session(void *panel_ptr, int i) {
    static QByteArray buffer;
    QStringList list = static_cast<TerminalPanel*>(panel_ptr)->konsoleSessions();
    if (i < 0 || i >= list.size()) return "";
    buffer = list.at(i).toUtf8();
    return buffer.constData();
}

int terminal_panel_import_konsole(void *panel_ptr, const char *session_path) {
    return static_cast<TerminalPanel*>(panel_ptr)->importKonsoleTab(QString(session_path));
}

void terminal_panel_copy(void *panel_ptr, int tab_idx) {
    static_cast<TerminalPanel*>(panel_ptr)->copySelection(tab_idx);
}

void terminal_panel_paste(void *panel_ptr, int tab_idx) {
    static_cast<TerminalPanel*>(panel_ptr)->pasteClipboard(tab_idx);
}

void terminal_panel_zoom_in(void *panel_ptr, int tab_idx) {
    static_cast<TerminalPanel*>(panel_ptr)->zoomIn(tab_idx);
}

void terminal_panel_zoom_out(void *panel_ptr, int tab_idx) {
    static_cast<TerminalPanel*>(panel_ptr)->zoomOut(tab_idx);
}

void terminal_panel_send_text(void *panel_ptr, int tab_idx, const char *text) {
    static_cast<TerminalPanel*>(panel_ptr)->sendText(tab_idx, QString(text));
}

const char* terminal_panel_working_dir(void *panel_ptr, int tab_idx) {
    static QByteArray buffer;
    QString dir = static_cast<TerminalPanel*>(panel_ptr)->workingDirectory(tab_idx);
    buffer = dir.toUtf8();
    return buffer.constData();
}

const char* terminal_panel_tab_text(void *panel_ptr, int tab_idx) {
    static QByteArray buffer;
    buffer = static_cast<TerminalPanel*>(panel_ptr)->tabText(tab_idx).toUtf8();
    return buffer.constData();
}

void terminal_panel_set_tab_text(void *panel_ptr, int tab_idx, const char *text) {
    static_cast<TerminalPanel*>(panel_ptr)->setTabText(tab_idx, QString(text));
}

const char* terminal_panel_save_state(void *panel_ptr) {
    static QByteArray buffer;
    buffer = static_cast<TerminalPanel*>(panel_ptr)->saveState().toUtf8();
    return buffer.constData();
}

int terminal_panel_restore_state(void *panel_ptr, const char *json) {
    return static_cast<TerminalPanel*>(panel_ptr)->restoreState(QString(json)) ? 1 : 0;
}

int terminal_panel_have_saved_state(void *panel_ptr) {
    return static_cast<TerminalPanel*>(panel_ptr)->haveSavedState() ? 1 : 0;
}

void terminal_panel_show_context_menu(void *panel_ptr, int tab_idx, int global_x, int global_y) {
    static_cast<TerminalPanel*>(panel_ptr)->showTabContextMenu(tab_idx, QPoint(global_x, global_y));
}

void terminal_panel_tear_off(void *panel_ptr, int tab_idx) {
    static_cast<TerminalPanel*>(panel_ptr)->tearOffTab(tab_idx);
}

void terminal_panel_detach_all(void *panel_ptr) {
    static_cast<TerminalPanel*>(panel_ptr)->detachAllToNewWindow();
}

void terminal_panel_new_window(void *panel_ptr) {
    static_cast<TerminalPanel*>(panel_ptr)->newWindow();
}

void terminal_panel_rename_tab(void *panel_ptr, int tab_idx) {
    static_cast<TerminalPanel*>(panel_ptr)->startTabRename(tab_idx);
}

void terminal_panel_prev_tab(void *panel_ptr) {
    static_cast<TerminalPanel*>(panel_ptr)->prevTab();
}

void terminal_panel_next_tab(void *panel_ptr) {
    static_cast<TerminalPanel*>(panel_ptr)->nextTab();
}

} // extern "C"
