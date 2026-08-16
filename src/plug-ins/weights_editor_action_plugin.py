from maya import cmds
from maya.api import OpenMaya


class UndoContext:
    """Context object to easily handle the undo state."""
    def __init__(self):
        self._state = cmds.undoInfo(query=True, state=True)

    def __enter__(self):
        if self._state:
            cmds.undoInfo(stateWithoutFlush=False)

    def __exit__(self, excType, excValue, traceback):
        if self._state:
            cmds.undoInfo(stateWithoutFlush=True)


class WeightsEditorAction(OpenMaya.MPxCommand):
    """
    More info: https://www.charactersetup.com/tutorials/undoable_python.html
    """
    commandName = "weightsEditorAction"
    callableObjectTemp = None  # Temporarily stores a class so that it can be passed to the instance's init.

    def __init__(self):
        super(WeightsEditorAction, self).__init__()
        self.callableObject = WeightsEditorAction.callableObjectTemp  # Store object so it can be called as undo/redo are triggered.

    def isUndoable(self) -> bool:
        """Mark that the class supports undo/redo."""
        return True

    def doIt(self, args):
        """Calls the object's 'doIt' method to do any heavy calculations, then calls 'redoIt' to apply it."""
        if self.callableObject and hasattr(self.callableObject, "doIt"):
            self.callableObject.doIt()
        self.redoIt()

    def redoIt(self):
        """Calls the object's 'redoIt' method to apply it."""
        if self.callableObject and hasattr(self.callableObject, "redoIt"):
            with UndoContext():
                self.callableObject.redoIt()

    def undoIt(self):
        """Calls the object's 'undoIt' method to revert whatever was done from 'redoIt'."""
        if self.callableObject and hasattr(self.callableObject, "undoIt"):
            with UndoContext():
                self.callableObject.undoIt()

    @classmethod
    def creator(cls):
        """Built-in MPxCommand creator method."""
        return cls()

    @classmethod
    def wrapCommand(cls):
        """
        Simplifies the original tutorial's logic by using a
        closure to overwrite the cmds function.
        """
        originalCommand = getattr(cmds, cls.commandName)

        def wrapped(callableObject):
            commandName = getattr(callableObject, "description", cls.commandName)  # Get the object's command name if available.
            cmds.undoInfo(openChunk=True, chunkName=commandName)
            try:
                cls.callableObjectTemp = callableObject  # Store object in this class so it can be passed to the instance.
                return originalCommand()
            finally:
                cmds.undoInfo(closeChunk=True)

        setattr(cmds, cls.commandName, wrapped)  # Replace the registered command in cmds so it calls the callable object.


def maya_useNewAPI():
    pass


def initializePlugin(mobject):
    mfnPlugin = OpenMaya.MFnPlugin(mobject)
    try:
        # Let maya create the command, and then replace it with a wrapped version that can accept a python class
        mfnPlugin.registerCommand(WeightsEditorAction.commandName, WeightsEditorAction.creator)
        WeightsEditorAction.wrapCommand()
    except:
        raise Exception(f"Unable to initialize: {WeightsEditorAction.commandName}")


def uninitializePlugin(mobject):
    mfnPlugin = OpenMaya.MFnPlugin(mobject)
    try:
        mfnPlugin.deregisterCommand(WeightsEditorAction.commandName)
    except:
        raise Exception(f"Unable to uninitialize: {WeightsEditorAction.commandName}")
