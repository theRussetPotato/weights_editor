"""
Drag and drop this file into your viewport to run the installer.
"""

import sys
import os
import time
import traceback
import shutil
import stat

import maya.cmds as cmds
import maya.OpenMaya as OpenMaya

try:
    # Try to load PySide2 for Maya 2023.
    from PySide2 import QtCore
    from PySide2 import QtGui
    from PySide2 import QtWidgets
except ModuleNotFoundError:
    # Try to load PySide6 for Maya 2025.
    from PySide6 import QtGui
    from PySide6 import QtCore
    from PySide6 import QtWidgets


PACKAGE_NAME = "weights_editor_tool"
PLUGIN_NAME = "weights_editor_action_plugin.py"


class Installer(QtWidgets.QDialog):

    """
    Widget to guide the user to install or uninstall the tool.
    """

    def __init__(self, parent: QtWidgets.QWidget = None) -> None:
        super().__init__(parent=parent)

        self.setWindowFlags(QtCore.Qt.Dialog)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)

        # Exit if it's unable to find the installer files relative to this file's path.
        currentDir = os.path.dirname(__file__)
        self._toolSrcPath = os.path.join(currentDir, "src", "scripts", PACKAGE_NAME).replace("\\", "/")
        self._pluginSrcPath = os.path.join(currentDir, "src", "plug-ins", PLUGIN_NAME).replace("\\", "/")
        if not os.path.exists(self._toolSrcPath):
            raise OSError(f"Unable to find installer files: {self._toolSrcPath}")
        if not os.path.exists(self._pluginSrcPath):
            raise OSError(f"Unable to find installer files: {self._pluginSrcPath}")

        self._createGui()

    @classmethod
    def run(cls) -> None:
        """Runs the installer and blocks the main thread."""
        installer = cls()
        installer.exec_()

    def _createGui(self) -> None:
        """Creates the interface's widgets and layouts."""
        prefsPath = cmds.about(preferences=True)
        prefsScriptsPath = os.path.join(prefsPath, "scripts").replace("\\", "/")
        prefsPluginsPath = os.path.join(prefsPath, "plug-ins").replace("\\", "/")

        scriptPaths = self._getPathsFromEnvVar("MAYA_SCRIPT_PATH")
        pluginPaths = self._getPathsFromEnvVar("MAYA_PLUG_IN_PATH")

        self._descriptionLabel = QtWidgets.QLabel("Use the fields below to pick the paths to install the tool's scripts and plugins.")

        self._tipIcon = QtWidgets.QLabel()
        icon = QtGui.QPixmap(f":/infoModal.png")
        icon = icon.scaledToHeight(24, QtCore.Qt.SmoothTransformation)
        self._tipIcon.setPixmap(icon)

        self._tipLabel = QtWidgets.QLabel(
            "It is recommended that you install the tool into your user preferences!\n"
            "These paths should be picked by default in the fields below.")

        self._tipLayout = QtWidgets.QHBoxLayout()
        self._tipLayout.addWidget(self._tipIcon, 0)
        self._tipLayout.addWidget(self._tipLabel, 1)

        self._tipFrame = QtWidgets.QFrame()
        self._tipFrame.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._tipFrame.setLayout(self._tipLayout)
        self._tipFrame.setStyleSheet("""
            QFrame {
                background-color: rgb(84, 104, 124);
                margin-left: 10;
                margin-right: 1 0;
            }
            
            QLabel {
                color: white;
            }
        """)

        self._scriptsPathLabel = QtWidgets.QLabel("Scripts Install Path:")
        self._scriptsPathLabel.setMinimumWidth(100)

        self._scriptsPathComboBox = QtWidgets.QComboBox()
        self._scriptsPathComboBox.addItems(scriptPaths)
        self._scriptsPathComboBox.setMaximumWidth(500)
        self._scriptsPathComboBox.view().setMinimumWidth(self._scriptsPathComboBox.sizeHint().width())
        if prefsScriptsPath in scriptPaths:
            self._scriptsPathComboBox.setCurrentText(prefsScriptsPath)

        self._scriptsPathLayout = QtWidgets.QHBoxLayout()
        self._scriptsPathLayout.addWidget(self._scriptsPathLabel, 0)
        self._scriptsPathLayout.addWidget(self._scriptsPathComboBox, 1)
        self._scriptsPathLayout.addStretch()

        self._pluginsPathLabel = QtWidgets.QLabel("Plugins Install Path:")
        self._pluginsPathLabel.setMinimumWidth(100)

        self._pluginsPathComboBox = QtWidgets.QComboBox()
        self._pluginsPathComboBox.addItems(pluginPaths)
        self._pluginsPathComboBox.setMaximumWidth(500)
        self._pluginsPathComboBox.view().setMinimumWidth(self._pluginsPathComboBox.sizeHint().width())
        if prefsPluginsPath in pluginPaths:
            self._pluginsPathComboBox.setCurrentText(prefsPluginsPath)

        self._pluginsPathLayout = QtWidgets.QHBoxLayout()
        self._pluginsPathLayout.addWidget(self._pluginsPathLabel, 0)
        self._pluginsPathLayout.addWidget(self._pluginsPathComboBox, 1)
        self._pluginsPathLayout.addStretch()

        self._cancelButton = QtWidgets.QPushButton("Cancel")
        self._cancelButton.setMinimumWidth(150)
        self._cancelButton.clicked.connect(self.close)

        self._uninstallButton = QtWidgets.QPushButton("Uninstall")
        self._uninstallButton.setMinimumWidth(150)
        self._uninstallButton.setStyleSheet("""
            QPushButton {
                background-color: rgb(124, 84, 84);
            }
        """)
        self._uninstallButton.clicked.connect(self._onUninstallClicked)

        self._installButton = QtWidgets.QPushButton("Install")
        self._installButton.setMinimumWidth(150)
        self._installButton.setStyleSheet("""
            QPushButton {
                background-color: rgb(84, 114, 84);
            }
        """)
        self._installButton.clicked.connect(self._onInstallClicked)

        self._installLayout = QtWidgets.QHBoxLayout()
        self._installLayout.addStretch()
        self._installLayout.addWidget(self._cancelButton)
        self._installLayout.addWidget(self._uninstallButton)
        self._installLayout.addWidget(self._installButton)
        self._installLayout.addStretch()

        self._mainLayout = QtWidgets.QVBoxLayout()
        self._mainLayout.addWidget(self._descriptionLabel)
        self._mainLayout.addWidget(self._tipFrame)
        self._mainLayout.addLayout(self._scriptsPathLayout)
        self._mainLayout.addLayout(self._pluginsPathLayout)
        self._mainLayout.addLayout(self._installLayout)
        self.setLayout(self._mainLayout)

        self.setWindowTitle("Weights Editor - Installer")
        self.resize(550, 0)

    def _getPathsFromEnvVar(self, envVar: str) -> list[str]:
        """Gets and returns paths from the supplied environment variable."""
        pathsValues = os.getenv(envVar, "")
        paths = [path.replace("\\", "/") for path in pathsValues.split(os.pathsep) if path]
        paths.sort()
        return paths

    def _uninstall(self) -> bool:
        """Uses Maya's paths to uninstall the Weights Editor. Returns True if it removed files."""
        uninstalled = False

        # Remove the tool if it exists.
        scriptPaths = self._getPathsFromEnvVar("MAYA_SCRIPT_PATH")
        for path in scriptPaths:
            toolPath = f"{path}/{PACKAGE_NAME}"
            if os.path.exists(toolPath):
                print(f"Removing {toolPath}")
                for root, dirs, files in os.walk(toolPath, topdown=False):
                    for name in files + dirs:
                        os.chmod(os.path.join(root, name), stat.S_IWUSR)
                shutil.rmtree(toolPath)
                uninstalled = True

        # Unload and remove the tool's plugin.
        if cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
            cmds.unloadPlugin(PLUGIN_NAME, force=True)
        if cmds.pluginInfo(PLUGIN_NAME, query=True, registered=True):
            cmds.pluginInfo(PLUGIN_NAME, edit=True, remove=True)

        # Remove the tool's plugin.
        pluginPaths = self._getPathsFromEnvVar("MAYA_PLUG_IN_PATH")
        for path in pluginPaths:
            pluginPath = f"{path}/{PLUGIN_NAME}"
            if os.path.exists(pluginPath):
                print(f"Removing {pluginPath}")
                os.remove(pluginPath)
                uninstalled = True

        return uninstalled

    def _install(self) -> None:
        """Installs the Weights Editor using paths from the widgets. An uninstall occurs first."""
        # Exit if installer files are missing.
        if not os.path.exists(self._toolSrcPath):
            raise OSError(f"Installer files are missing from path {self._toolSrcPath}")
        if not os.path.exists(self._pluginSrcPath):
            raise OSError(f"Installer files are missing from path {self._pluginSrcPath}")

        # First uninstall so it can be cleanly replaced.
        uninstalled = self._uninstall()
        if uninstalled:
            # Windows may throw an 'access denied' exception doing a copytree right after a rmtree.
            # Forcing it a slight delay seems to solve it.
            time.sleep(1)

        # Clear this tool from modules so it can reload.
        for key in list(sys.modules):
            if "weights_editor_tool" in key:
                del sys.modules[key]

        # Copy tool's directory over.
        scriptsInstallPath = self._scriptsPathComboBox.currentText()
        toolInstallPath = f"{scriptsInstallPath}/{PACKAGE_NAME}"
        print(f"Copying package: {self._toolSrcPath} >> {toolInstallPath}")
        shutil.copytree(self._toolSrcPath, toolInstallPath)

        # Copy tool's plugin over.
        pluginsDirInstallPath = self._pluginsPathComboBox.currentText()
        if not os.path.exists(pluginsDirInstallPath):
            print(f"Creating plugin folder {pluginsDirInstallPath}")
            os.makedirs(pluginsDirInstallPath, exist_ok=True)
        pluginInstallPath = f"{pluginsDirInstallPath}/{PLUGIN_NAME}"
        print(f"Copying plugin: {self._pluginSrcPath} >> {pluginInstallPath}")
        shutil.copy(self._pluginSrcPath, pluginInstallPath)

    def _onUninstallClicked(self) -> None:
        """Triggered when clicking the uninstall button."""
        try:
            self._uninstall()

            QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Information,
                "Uninstall is complete",
                "The Weights Editor has been uninstalled.",
                buttons=QtWidgets.QMessageBox.Ok,
                parent=self).exec_()
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))
        finally:
            self.close()

    def _onInstallClicked(self) -> None:
        """Triggered when clicking the install button."""
        try:
            self._install()

            QtWidgets.QMessageBox(
                QtWidgets.QMessageBox.Information,
                "Install is complete",
                "The Weights Editor has been installed!<br>"
                "Please restart Maya to register the tool's plugin.<br>"
                "<br>"
                "Copy this Python command to run it later:<br>"
                "<i>from weights_editor_tool import weights_editor<br>"
                "weights_editor.run()</i>",
                buttons=QtWidgets.QMessageBox.Ok,
                parent=self).exec_()
        except Exception as err:
            print(traceback.format_exc())
            OpenMaya.MGlobal.displayError(str(err))
        finally:
            self.close()


def onMayaDroppedPythonFile(*args) -> None:
    """Triggers when this file is dropped onto one of Maya's viewports."""
    # Exit if it's unable to find the installer files relative to this file's path.
    currentDir = os.path.dirname(__file__)
    toolSrcPath = os.path.join(currentDir, "src", "scripts", PACKAGE_NAME)
    pluginSrcPath = os.path.join(currentDir, "src", "plug-ins", PLUGIN_NAME)
    if not os.path.exists(toolSrcPath):
        raise OSError(f"Unable to find installer files: {toolSrcPath}")
    if not os.path.exists(pluginSrcPath):
        raise OSError(f"Unable to find installer files: {pluginSrcPath}")

    # Run the installer window.
    Installer.run()
