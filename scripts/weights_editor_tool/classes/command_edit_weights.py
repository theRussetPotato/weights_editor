from maya import cmds

from PySide2 import QtWidgets

from weights_editor_tool.widgets import weights_table_view


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

        self._editor_cls = editor_cls
        self._skip_first_redo = skip_first_redo
        self._obj = obj
        self._old_skin_data = old_skin_data
        self._new_skin_data = new_skin_data
        self._vert_indexes = vert_indexes
        self._table_selection = table_selection

    def redo(self):
        if self._skip_first_redo:
            self._skip_first_redo = False
            return

        if not self._obj or not cmds.objExists(self._obj):
            return

        weights_view = self._editor_cls.instance.get_active_weights_view()
        old_column_count = weights_view.horizontalHeader().count()
        weights_view.begin_update()

        self._editor_cls.instance.obj.skin_data = self._new_skin_data
        self._editor_cls.instance.obj.apply_current_skin_weights(self._vert_indexes, normalize=True)
        self._editor_cls.instance.update_vert_colors(vert_filter=self._vert_indexes)
        self._editor_cls.instance.collect_display_infs()

        weights_view.load_table_selection(self._table_selection)
        weights_view.color_headers()

        weights_view.end_update()

        if isinstance(weights_view, weights_table_view.TableView) and \
                weights_view.horizontalHeader().count() != old_column_count:
            weights_view.fit_headers_to_contents()

    def undo(self):
        if not self._obj or not cmds.objExists(self._obj):
            return

        weights_view = self._editor_cls.instance.get_active_weights_view()
        old_column_count = weights_view.horizontalHeader().count()
        weights_view.begin_update()

        self._editor_cls.instance.obj.skin_data = self._old_skin_data
        self._editor_cls.instance.obj.apply_current_skin_weights(self._vert_indexes, normalize=True)
        self._editor_cls.instance.update_vert_colors(vert_filter=self._vert_indexes)
        self._editor_cls.instance.collect_display_infs()

        weights_view.load_table_selection(self._table_selection)
        weights_view.color_headers()

        weights_view.end_update()

        if isinstance(weights_view, weights_table_view.TableView) and \
                weights_view.horizontalHeader().count() != old_column_count:
            weights_view.fit_headers_to_contents()
