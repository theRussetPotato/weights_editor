<p align="center">
  <img src="https://user-images.githubusercontent.com/14979497/142756771-08a485c8-a2ce-40aa-9622-a09039c98f81.png" />
</p>

<p align="center">
A skin weights component editor inspired from Softimage.
</p>

# Interface

![weightsEditorTable](https://user-images.githubusercontent.com/14979497/148098205-d37b2533-c589-45fd-a84b-643963f1704c.png)<br>
_Interface using the table view_

<br>

![weightsEditorList](https://user-images.githubusercontent.com/14979497/148098259-c2435bb9-cfff-42a7-8937-802cba182626.png)<br>
_Interface using the list view_

## Features

- Editable table and list views to quickly set weights with selected components (verts, edges, faces)
- Buttons with preset values to add, subtract, scale, or set weights (buttons are customizable)
- Quickly lock or unlock selected influences by pressing space
- Influence list on the side
- Displays weights in different color themes
- Weight utilities to prune, smooth, mirror, and copy/paste vertex weights
- Weights can be exported to a file
- Weights can be imported via point order, or by world space positions of the mesh's vertices. Weights can also import onto selected vertices, so you can maintain existing skin weights outside of the selection.
- Button to flood full weights to the vertex's closest influence for quick blocking
- All operations support undo/redo
- Temporary hotkeys that can be re-assigned

## Supported versions

In short, Maya 2017 and above is supported.<br>
Release v2.0.0 was heavily used in production in Maya 2018 Extension 4.<br>
It was also rewritten to work with Python 3 so it will run on Maya 2022.<br>

For earlier versions of Maya using PySide (Qt4), only release v1.0.0 will work as future releases will only support PySide2 (Qt5).

## Installation

- Open up a session of Maya<br>
- Drag and drop the installer file `DRAG_AND_DROP_INSTALLER.py` into the viewport. Please do not move this file, it uses relative paths to copy over the files.<br>
- Follow the instructions to complete the installation.

If you prefer to manually install it then simply copy the `weights_editor_tool` directory to wherever your Python path is pointing to.

After installation you can immediately launch the tool by executing in the script editor:

```
from weights_editor_tool import weights_editor
weights_editor.run()
```

## Dependencies

This tool doesn't require any extra libraries and uses all native modules that ship with Maya.

An optional plugin is needed to perform a smooth with all influences.<br>
By default this feature will be disabled if the plugin is not loaded.

The plugin is `smoothSkinClusterWeight` by <a href='http://www.braverabbit.com'>Ingo Clemens</a>.<br>
It's fantastic, free, and you can download it <a href='https://www.braverabbit.com/braverabbit/tools/brsmoothweights/'>here</a>.

## Reporting a bug

If you run into any errors during installation or using the tool itself, then please <a href='https://github.com/theRussetPotato/weights_editor/issues'>create a new issue</a> from this repository.

Please include the following:

* Your operating system (Windows, Linux, Mac)
* Your version of Maya
* If possible, open up the script editor and copy & paste the error message.
* If possible, include a screenshot showing the error.
* Include any steps that will reproduce the error.

## Requests and new features

If you have any ideas to improve this tool then feel free to <a href='https://github.com/theRussetPotato/weights_editor/issues'>send any suggestions</a>!

## Credits and thanks

Enrique Caballero and John Lienard for pushing me to make this.<br>
Ingo Clemens (Brave Rabbit) for his <a href='https://www.braverabbit.com/braverabbit/tools/brsmoothweights/'>smoothSkinClusterWeight plugin</a>.<br>
Tyler Thornock for his <a href='http://www.charactersetup.com/tutorial_skinWeights.html'>tutorial</a> on a faster approach to get/set skin weights.<br>

### Happy skinning :)
