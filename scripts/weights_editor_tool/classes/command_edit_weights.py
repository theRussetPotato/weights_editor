import maya.cmds as cmds

from PySide2 import QtWidgets

from weights_editor_tool import weights_editor_utils as utils


class CommandEditWeights(QtWidgets.QUndoCommand):
    """
    Command to edit skin weights.

    Args:
        editor_cls (WeightsEditor)
        description (string): The label to show up to describe this action.
        obj (string): An object with a skinCluster to edit weights on.
        old_skin_data (dict): A copy of skin data to revert to.
        new_skin_data (dict): A copy of skin data to set to.
        vert_indexes (int[]): A list of indexes to operate on.
        table_selection (dict): Selection data to revert back to.
        skip_first_redo (bool): Qt forces redo to be executed right away. Enable this to skip it if it's not needed.
    """

    def __init__(self, editor_cls, description, obj, old_skin_data, new_skin_data, vert_indexes,
                 table_selection, skip_first_redo=False, parent=None):
        super(CommandEditWeights, self).__init__(description, parent=parent)

        self.editor_cls = editor_cls
        self.skip_first_redo = skip_first_redo
        self.obj = obj
        self.old_skin_data = old_skin_data
        self.new_skin_data = new_skin_data
        self.vert_indexes = vert_indexes
        self.table_selection = table_selection

    def redo(self):
        if self.skip_first_redo:
            self.skip_first_redo = False
            return

        if not self.obj or not cmds.objExists(self.obj):
            return

        weights_view = self.editor_cls.instance.get_active_weights_view()

        old_column_count = weights_view.horizontalHeader().count()

        weights_view.begin_update()

        self.editor_cls.instance.skin_data = self.new_skin_data

        utils.set_skin_weights(self.obj, self.new_skin_data, self.vert_indexes, normalize=True)

        self.editor_cls.instance.update_vert_colors(vert_filter=self.vert_indexes)

        self.editor_cls.instance.collect_display_infs()

        weights_view.load_table_selection(self.table_selection)

        weights_view.end_update()

        if weights_view.view_type == "table" and weights_view.horizontalHeader().count() != old_column_count:
            weights_view.fit_headers_to_contents()

    def undo(self):
        if not self.obj or not cmds.objExists(self.obj):
            return

        weights_view = self.editor_cls.instance.get_active_weights_view()

        old_column_count = weights_view.horizontalHeader().count()

        weights_view.begin_update()

        self.editor_cls.instance.skin_data = self.old_skin_data
        utils.set_skin_weights(self.obj, self.old_skin_data, self.vert_indexes, normalize=True)

        self.editor_cls.instance.update_vert_colors(vert_filter=self.vert_indexes)

        self.editor_cls.instance.collect_display_infs()

        weights_view.load_table_selection(self.table_selection)

        weights_view.end_update()

        if weights_view.view_type == "table" and weights_view.horizontalHeader().count() != old_column_count:
            weights_view.fit_headers_to_contents()
