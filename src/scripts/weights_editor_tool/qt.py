try:
    import shiboken2 as shiboken
except ModuleNotFoundError:
    import shiboken6 as shiboken
except ModuleNotFoundError:
    raise NotImplementedError(f"Unable to import 'shiboken2' or 'shiboken6'")


try:
    # Try to load PySide2 for Maya 2023.
    from PySide2 import QtGui
    from PySide2 import QtCore
    from PySide2 import QtWidgets
    from PySide2 import QtNetwork
    QT_VERSION = 2
    QShortcut = QtWidgets.QShortcut
    QAction = QtWidgets.QAction
    QActionGroup = QtWidgets.QActionGroup
except ModuleNotFoundError:
    # Try to load PySide6 for Maya 2025.
    from PySide6 import QtGui
    from PySide6 import QtCore
    from PySide6 import QtWidgets
    from PySide6 import QtNetwork
    QT_VERSION = 6
    QShortcut = QtGui.QShortcut
    QAction = QtGui.QAction
    QActionGroup = QtGui.QActionGroup

    setattr(QtCore.Qt, "BackgroundColorRole", getattr(QtCore.Qt, "BackgroundRole"))
    setattr(QtCore.Qt, "TextColorRole", getattr(QtCore.Qt, "ForegroundRole"))

    '''qtEnumMappings = [
        QtCore.Qt.Orientation,
        QtCore.Qt.WindowType,
        QtCore.Qt.WidgetAttribute,
        QtCore.Qt.FocusPolicy,
        QtCore.Qt.TransformationMode,
        QtCore.Qt.ShortcutContext,
        QtCore.Qt.TextInteractionFlag,
        QtCore.Qt.CursorShape,
        QtCore.Qt.PenStyle,
        QtCore.Qt.ContextMenuPolicy,
        QtCore.Qt.AlignmentFlag,
        QtCore.Qt.MouseButton,
        QtCore.Qt.GlobalColor,
        QtCore.Qt.ItemDataRole,
        QtCore.Qt.ToolTip,
        QtCore.Qt.SortOrder
    ]

    for enumClass in qtEnumMappings:
        for enumItem in enumClass:
            setattr(QtCore.Qt, enumItem.name, enumItem)'''


except ModuleNotFoundError:
    raise NotImplementedError(f"Unable to import 'PySide2' or 'PySide6'")