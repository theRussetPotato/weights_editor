<p align="center">
  <img src="https://user-images.githubusercontent.com/14979497/142756771-08a485c8-a2ce-40aa-9622-a09039c98f81.png" />
</p>

<p align="center">
A skin weights component editor inspired from Softimage.
</p>

# 🖥️ Interface

![weightsEditorList](https://github.com/theRussetPotato/weights_editor/assets/14979497/4366b311-854a-418b-88ac-7476ab466614)<br>
_The interface using the list view with averaged values_

<br>

![weightsEditorTable](https://github.com/theRussetPotato/weights_editor/assets/14979497/a1900dd0-8f7b-4b72-b7cd-a8d096662a8c)<br>
_The interface using the table view for more granular control_

## ⭐ Features

- Editable table and list views to quickly set weights with selected components (verts, edges, faces)
- Buttons with preset values to add, subtract, scale, or set weights (buttons are customizable)
- Quickly lock or unlock selected influences from the list/table/influence views by pressing space
- Influence list on the side
  - Select the influence
  - Select all vertexes weighted to the influence
- Displays weights in different color themes
  - 3DsMax style (from blue to red)
  - Maya style (from red to white)
  - Softimage style (displays all influences at once)
  - Maximum influences (colors vertexes red if they are over a specific influence count)
- Weight utilities
  - Prune weights under a specified value
  - Prune weights over a specified influence count
  - Smooth weights using the vert's influences
  - Smooth weights with the verts neighboring influences (using Brave Rabbit's plugin)
  - Mirror selected vertexes or all weights
  - Copy & paste vertex weights
- Skin weights exporter, which include dual-quaternion weights
- Skin weights importer
  - Import via point order
  - Import via world space positions from the mesh's vertices
  - Weights can also import onto selected vertices only, so you can maintain existing skin weights outside of the selection.
- Button to flood full weights to the vertex's closest influence to begin quick blocking
- All operations support undo/redo
- Most operations are assigned to hotkeys, which can be re-assigned

https://user-images.githubusercontent.com/14979497/148168582-5fb3e761-e70d-4904-be8e-a12da03faf3a.mp4

_Exporting weights then importing them onto a different object via world positions_

https://user-images.githubusercontent.com/14979497/148170835-fc301bd2-1dce-4f23-9632-02eb80eaa298.mp4

_Importing weights onto selected vertices_

## ❤️ Supported Versions

In short, Maya 2017 and above is supported.<br>
Release v2.0.0 was heavily used in production in Maya 2018 Extension 4.<br>
It was also rewritten to work with Python 3 so it will run on Maya 2022.<br>

For earlier versions of Maya using PySide (Qt4), only release v1.0.0 will work as future releases will only support PySide2 (Qt5).

## ➕ Installation

- Open up a session of Maya<br>
- Drag and drop the installer file `DRAG_AND_DROP_INSTALLER.py` into the viewport. Please do not move this file, it uses relative paths to copy over the files.<br>
- Follow the instructions to complete the installation.

If you prefer to manually install it then simply copy the `weights_editor_tool` directory to wherever your Python path is pointing to.

After installation you can immediately launch the tool by executing in the script editor:

```
from weights_editor_tool import weights_editor
weights_editor.run()
```

## 👪 Dependencies

This tool doesn't require any extra libraries and uses all native modules that ship with Maya.

An optional plugin is needed to perform a smooth with all influences.<br>
By default this feature will be disabled if the plugin is not loaded.

The plugin is `smoothSkinClusterWeight` by <a href='http://www.braverabbit.com'>Ingo Clemens</a>.<br>
It's fantastic, free, and you can download it <a href='https://www.braverabbit.com/braverabbit/tools/brsmoothweights/'>here</a>.

## 🐛 Reporting a Bug

If you run into any errors during installation or using the tool itself, then please <a href='https://github.com/theRussetPotato/weights_editor/issues'>create a new issue</a> from this repository.

Please include the following:

* Your operating system (Windows, Linux, Mac)
* Your version of Maya
* If possible, open up the script editor and copy & paste the error message.
* If possible, include a screenshot showing the error.
* Include any steps that will reproduce the error.

## ✉️ Requests and New Features

If you have any ideas to improve this tool then feel free to <a href='https://github.com/theRussetPotato/weights_editor/issues'>send any suggestions</a>!

## 🙏 Credits and Thanks

Enrique Caballero and John Lienard for pushing me to make this.<br>
Ingo Clemens (Brave Rabbit) for his <a href='https://www.braverabbit.com/braverabbit/tools/brsmoothweights/'>smoothSkinClusterWeight plugin</a>.<br>

### Happy skinning 😍🎨🖌️
