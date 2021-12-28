from PySide2 import QtCore
from PySide2 import QtGui
from PySide2 import QtWidgets

from weights_editor_tool import constants
from weights_editor_tool import weights_editor_utils as utils


class AboutDialog(QtWidgets.QDialog):

    def __init__(self, version, parent=None):
        QtWidgets.QDialog.__init__(self, parent=parent)

        self._version = version

        self._create_gui()

    def _wrap_groupbox(self, title, msg):
        label = QtWidgets.QLabel(msg, parent=self)
        label.setWordWrap(True)
        label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse | QtCore.Qt.LinksAccessibleByMouse)
        label.setCursor(QtGui.QCursor(QtCore.Qt.IBeamCursor))
        label.setOpenExternalLinks(True)

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(label)

        groupbox = QtWidgets.QGroupBox(title, parent=self)
        groupbox.setLayout(layout)

        return groupbox

    def _create_gui(self):
        self._logo_img = QtWidgets.QLabel(parent=self)
        self._logo_img.setAlignment(QtCore.Qt.AlignCenter)
        self._logo_img.setPixmap(utils.load_pixmap("about/logo.png", width=125))

        self._version_label = QtWidgets.QLabel("Version v{}".format(self._version), parent=self)
        self._version_label.setAlignment(QtCore.Qt.AlignCenter)
        self._version_label.setStyleSheet(
            "QLabel {font-weight: bold; color: white;}")

        self._table_tips_groupbox = self._wrap_groupbox(
            "Using weights list / table",
            "- Right-click a cell to edit its value<br>"
            "- Press space to toggle locks on selected influences<br>"
            "- Click top or side headers to select rows or columns<br>"
            "- Middle-click influence header to display that influence<br>"
            "- Right-click influence header to trigger a menu")

        self._inf_list_tips_groupbox = self._wrap_groupbox(
            "Using influence list",
            "- Press space to toggle locks on selected influences<br>"
            "- Middle-click header to display that influence<br>"
            "- Right-click to trigger a menu<br>"
            "- Double-click to select the influence")

        self._developed_by_groupbox = self._wrap_groupbox(
            "Developed by",
            "<b>Jason Labbe</b>")

        self._special_thanks_groupbox = self._wrap_groupbox(
            "Special thanks to",
            "<b>Enrique Caballero</b> and <b>John Lienard</b> for pushing me to make this")

        self._bugs_groupbox = self._wrap_groupbox(
            "Bugs and features",
            "Please report any bugs on its <b><a href='{url}'>GitHub issues page</a></b>".format(url=constants.GITHUB_ISSUES))

        self._scroll_layout = QtWidgets.QVBoxLayout()
        self._scroll_layout.addWidget(self._table_tips_groupbox)
        self._scroll_layout.addWidget(self._inf_list_tips_groupbox)
        self._scroll_layout.addWidget(self._developed_by_groupbox)
        self._scroll_layout.addWidget(self._special_thanks_groupbox)
        self._scroll_layout.addWidget(self._bugs_groupbox)
        self._scroll_layout.addStretch()

        self._scroll_frame = QtWidgets.QFrame(parent=self)
        self._scroll_frame.setLayout(self._scroll_layout)

        self._scroll_area = QtWidgets.QScrollArea(parent=self)
        self._scroll_area.setFocusPolicy(QtCore.Qt.NoFocus)
        self._scroll_area.setStyleSheet("QScrollArea {border: none;}")
        self._scroll_area.setWidget(self._scroll_frame)
        self._scroll_area.setWidgetResizable(True)

        self._ok_button = QtWidgets.QPushButton("OK", parent=self)
        self._ok_button.clicked.connect(self.close)

        self._ok_layout = QtWidgets.QHBoxLayout()
        self._ok_layout.addStretch()
        self._ok_layout.addWidget(self._ok_button)
        self._ok_layout.addStretch()

        self._main_layout = QtWidgets.QVBoxLayout()
        self._main_layout.addWidget(self._logo_img)
        self._main_layout.addWidget(self._version_label)
        self._main_layout.addWidget(self._scroll_area)
        self._main_layout.addLayout(self._ok_layout)
        self.setLayout(self._main_layout)

        self.setWindowTitle("About Weights Editor")
        self.resize(400, 500)

    @classmethod
    def launch(cls, version, parent):
        dialog = cls(version, parent=parent)
        dialog.exec_()
        return dialog
