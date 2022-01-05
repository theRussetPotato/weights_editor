from maya import cmds

from PySide2 import QtWidgets


class CommandLockInfs(QtWidgets.QUndoCommand):
    """
    Command to toggle influence locks.

    Args:
        editor_cls (WeightsEditor)
        description (string): The label to show up to describe this action.
        infs (string[]): A list of influence objects to operate on.
        enabled (bool): The state to set all the new locks to.
    """

    def __init__(self, editor_cls, description, infs, enabled, parent=None):
        super(CommandLockInfs, self).__init__(description, parent=parent)

        self._editor_cls = editor_cls

        # {inf_name, default_lock_state}
        self._infs = {
            inf: cmds.getAttr("{0}.lockInfluenceWeights".format(inf))
            for inf in infs}

        self._enabled = enabled

    def lock_infs(self, use_redo_value):
        weights_view = self._editor_cls.instance.get_active_weights_view()

        weights_view.begin_update()
        self._editor_cls.instance.inf_list.begin_update()

        for inf, enabled in self._infs.items():
            if not cmds.objExists(inf) or inf not in self._editor_cls.instance.obj.infs:
                continue

            if use_redo_value:
                lock = self._enabled
            else:
                lock = enabled

            cmds.setAttr("{0}.lockInfluenceWeights".format(inf), lock)

            inf_index = self._editor_cls.instance.obj.infs.index(inf)

            self._editor_cls.instance.locks[inf_index] = lock

        self._editor_cls.instance.inf_list.end_update()
        weights_view.end_update()

    def redo(self):
        self.lock_infs(True)

    def undo(self):
        self.lock_infs(False)
