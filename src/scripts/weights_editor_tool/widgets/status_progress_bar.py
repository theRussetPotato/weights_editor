from maya import cmds
from maya import mel


class StatusProgressBar:
    """
    Manages Maya's main status bar progress indicator.
    This class wraps the global `$gMainProgressBar` MEL variable into a reusable object, providing an interface for long-running operations.
    """

    def __init__(self, name: str, count: int, interruptable: bool = True) -> None:
        """
        Initializes the progress bar state and fetches the global Maya UI pointer.

        Args:
            name (str): The text description to display next to the bar.
            count (int): The total number of steps in the operation.
            interruptable (bool): If True, allows the user to cancel by hitting 'Esc'.
        """
        if count <= 0:
            raise ValueError("Progress bar count cannot be set to 0.")

        self._name = name
        self._count = count
        self._progressBar = None
        self._inGuiMode = not cmds.about(batch=True)
        self._interruptable = interruptable

        if self._inGuiMode:
            self._progressBar = mel.eval("$tmp = $gMainProgressBar")

    def __enter__(self):
        """
        Enables use as a context manager, automatically calling start().

        Returns:
            The instance of the progress bar.
        """
        return self.start()

    def __exit__(self, type, value, traceback):
        """
        Ensures the progress bar is closed when exiting the context.
        """
        self.end()

    # Progress bar needs to reset to prevent cancelling auto-triggering.
    def _reset(self) -> None:
        """
        Clears the progress bar state to prevent lingering cancellation flags.
        """
        cmds.progressBar(self._progressBar, edit=True, beginProgress=True, isInterruptable=True)
        cmds.progressBar(self._progressBar, edit=True, endProgress=True)

    def start(self) -> 'StatusProgressBar':
        """
        Initializes the UI component in Maya and sets the maximum step count.

        Returns:
            The instance of the progress bar.
        """
        if self._inGuiMode:
            self._reset()

            cmds.progressBar(
                self._progressBar,
                edit=True,
                beginProgress=True,
                isInterruptable=self._interruptable,
                status=f"{self._name} ...",
                maxValue=self._count,
                backgroundColor=[0, 0, 0])

        return self

    def end(self) -> None:
        """
        Finalizes the progress bar and returns control to the Maya UI.
        """
        if self._inGuiMode:
            cmds.progressBar(self._progressBar, edit=True, endProgress=True)

    def wasCancelled(self) -> bool:
        """
        Checks if the user has pressed the 'Esc' key to halt the operation.

        Returns:
            True if the operation was cancelled, False otherwise.
        """
        if self._inGuiMode and self._interruptable:
            return cmds.progressBar(self._progressBar, query=True, isCancelled=True)
        else:
            return False

    def next(self) -> None:
        """
        Increments the progress bar by a single step.
        """
        if self._inGuiMode:
            cmds.progressBar(self._progressBar, edit=True, step=1)
