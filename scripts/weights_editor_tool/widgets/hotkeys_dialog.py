from itertools import combinations

from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils
from weights_editor_tool.classes.hotkey import Hotkey


class HotkeysDialog(QtWidgets.QDialog):

    def __init__(self, hotkeys, parent=None):
        QtWidgets.QDialog.__init__(self, parent=parent)

        self._hotkey_edits = []

        self._create_gui(hotkeys)

    def _create_gui(self, hotkeys):
        self._menu_bar = QtWidgets.QMenuBar(self)
        self._menu_bar.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        self._settings_menu = QtWidgets.QMenu("&Tool settings", parent=self)
        self._menu_bar.addMenu(self._settings_menu)

        self._reset_to_defaults_action = QtWidgets.QAction("Reset to defaults", self)
        self._reset_to_defaults_action.triggered.connect(self._reset_to_defaults_on_triggered)
        self._settings_menu.addAction(self._reset_to_defaults_action)

        self._main_layout = QtWidgets.QVBoxLayout()
        self._main_layout.addWidget(self._menu_bar)

        for hotkey in hotkeys:
            label = QtWidgets.QLabel(hotkey.caption, parent=self)
            label.setFixedWidth(150)

            key_edit = HotkeyEdit(hotkey.copy(), parent=self)
            key_edit.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
            self._hotkey_edits.append(key_edit)

            hotkey_layout = QtWidgets.QHBoxLayout()
            hotkey_layout.addWidget(label)
            hotkey_layout.addWidget(key_edit)
            hotkey_layout.addStretch()

            self._main_layout.addLayout(hotkey_layout)

        self._apply_button = QtWidgets.QPushButton("Apply changes", parent=self)
        self._apply_button.clicked.connect(self._accept_on_clicked)

        self._cancel_button = QtWidgets.QPushButton("Cancel", parent=self)
        self._cancel_button.clicked.connect(self.reject)

        self._buttons_layout = QtWidgets.QHBoxLayout()
        self._buttons_layout.addWidget(self._apply_button)
        self._buttons_layout.addWidget(self._cancel_button)

        self._main_frame = QtWidgets.QFrame(parent=self)
        self._main_frame.setLayout(self._main_layout)

        self._scroll_area = QtWidgets.QScrollArea(parent=self)
        self._scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self._scroll_area.setStyleSheet("QScrollArea {border: none;}")
        self._scroll_area.setWidget(self._main_frame)
        self._scroll_area.setWidgetResizable(True)

        self._tooltip_label = QtWidgets.QLabel(
            "These hotkeys will temporarily override your native hotkeys until the tool is closed.",
            parent=self)
        self._tooltip_label.setWordWrap(True)
        self._tooltip_label.setStyleSheet("""
            QLabel {
                padding: 10px;
                font-style: italic;
            }
        """)

        self._menu_layout = QtWidgets.QVBoxLayout()
        self._menu_layout.setContentsMargins(0, 0, 0, 0)
        self._menu_layout.addWidget(self._menu_bar)
        self._menu_layout.addWidget(self._tooltip_label)
        self._menu_layout.addWidget(self._scroll_area)
        self._menu_layout.addLayout(self._buttons_layout)
        self.setLayout(self._menu_layout)

        self.setWindowTitle("Edit Hotkeys")
        self.resize(350, 400)

    @classmethod
    def launch(cls, hotkeys, parent):
        dialog = cls(hotkeys, parent=parent)
        return dialog.exec_(), dialog

    def serialize(self):
        return [
            hotkey_edit.hotkey
            for hotkey_edit in self._hotkey_edits
        ]

    def _check_for_duplicate_hotkeys(self):
        for edit, other_edit in combinations(self._hotkey_edits, 2):
            if edit.hotkey.matches(other_edit.hotkey):
                raise RuntimeError(
                    "`{hotkey1}` is clashing with another hotkey `{hotkey2}`".format(
                        hotkey1=edit.hotkey.caption, hotkey2=other_edit.hotkey.caption))

    def _reset_to_defaults_on_triggered(self):
        for hotkey_edit in self._hotkey_edits:
            hotkey_edit.reset_to_default()

    def _accept_on_clicked(self):
        try:
            self._check_for_duplicate_hotkeys()
            self.accept()
        except Exception as err:
            utils.show_error_msg("Error!", str(err), self.parent())


class HotkeyEdit(QtWidgets.QLineEdit):

    key_pressed = QtCore.Signal(QtWidgets.QLineEdit, QtGui.QKeyEvent)

    def __init__(self, hotkey, parent=None):
        self.hotkey = hotkey

        QtWidgets.QLineEdit.__init__(self, self.hotkey.key_to_string(), parent=parent)

    def keyPressEvent(self, key_event):
        if not key_event.text():
            return

        key_values = Hotkey.serialize_key_event(key_event)

        self.hotkey.shift = key_values["shift"]
        self.hotkey.ctrl = key_values["ctrl"]
        self.hotkey.alt = key_values["alt"]
        self.hotkey.key = key_values["key"]

        self.setText(self.hotkey.key_to_string())

    def mousePressEvent(self, event):
        self.selectAll()

    def reset_to_default(self):
        self.hotkey.reset_to_default()
        self.setText(self.hotkey.key_to_string())
