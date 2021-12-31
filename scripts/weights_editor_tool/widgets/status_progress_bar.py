from maya import cmds
from maya import mel


class StatusProgressBar:

    """
    Creates a progress bar in Maya's status bar.

    Args:
        name(str): What is to be displayed.
        count(int): The length to iterate over.
    """

    def __init__(self, name, count, interruptable=True):
        self._name = name
        self._count = count
        self._progress_bar = None
        self._in_gui_mode = not cmds.about(batch=True)
        self._interruptable = interruptable

        if self._in_gui_mode:
            self._progress_bar = mel.eval("$tmp = $gMainProgressBar")

    def __enter__(self):
        return self.start()

    def __exit__(self, type, value, traceback):
        self.end()

    # Progress bar needs to reset to prevent cancelling auto-triggering.
    def _reset(self):
        cmds.progressBar(self._progress_bar, edit=True, beginProgress=True, isInterruptable=True)
        cmds.progressBar(self._progress_bar, edit=True, endProgress=True)

    def start(self):
        if self._in_gui_mode:
            self._reset()

            cmds.progressBar(
                self._progress_bar,
                edit=True,
                beginProgress=True,
                isInterruptable=self._interruptable,
                status="{0} ...".format(self._name),
                maxValue=self._count,
                bgc=[0, 0, 0])

        return self

    def end(self):
        if self._in_gui_mode:
            cmds.progressBar(self._progress_bar, edit=True, endProgress=True)

    def was_cancelled(self):
        if self._in_gui_mode and self._interruptable:
            return cmds.progressBar(self._progress_bar, q=True, isCancelled=True)
        else:
            return False

    def next(self):
        if self._in_gui_mode:
            cmds.progressBar(self._progress_bar, edit=True, step=1)
