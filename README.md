# Weights Editor

A tool to edit skin weights on a vertex level.

It was heavily influenced by Softimage's weight editor.

At the moment it has been tested and used in production in Maya 2016.5 and 2018. As a result, this tool is supported for both Qt4 and Qt5.

<img src="http://www.jasonlabbe3d.com/resources/images/github/weights_editor_window.jpg" width="500">

## Installation

Open up a session of Maya then drag and drop the installer file DRAG_AND_DROP_INSTALLER.py into the viewport. Please do not move this file, it uses relative paths to copy over the files.
Follow the instructions to complete the installation.

If you chose the option to add a shelf button then Maya needs to restart in order for it to show up.

After installation you can immediately test if it's working ok by executing the following in the script editor to run the tool:

```
from weights_editor_tool import weights_editor
weights_editor.run()
```

If you prefer to manually install it then simply copy the `weights_editor_tool` directory to wherever your Python path is pointing to.

## Dependencies

There's no need to install any extra libraries as this tool uses all native Python modules that ship with Maya.

The tool does use a plugin to do a smooth with all influcences, but is not necessary to install. By default this feature will be disabled if the plugin is not loaded.

The plugin is smoothSkinClusterWeight by Ingo Clemens (Brave Rabbit). You can find the appropriate plugin for your OS and Maya version <a href='http://www.braverabbit.com/smoothskinclusterweight'>here</a>.

## Reporting a bug

If you run into any errors during installation or using the tool itself, then please send an e-mail to jasonlabbe@gmail.com
Please include the following:

* Your operating system
* Your version of Maya
* If possible, open up the script editor and copy & paste the error message.
* Include any steps that will reproduce the error.

## Requests and new features

If you have any ideas to improve this tool then feel free to send any suggestions!

## Credits and thanks

Enrique Caballero and John Lienard for pushing me to make this.

Ingo Clemens (Brave Rabbit) for his <a href='http://www.braverabbit.com/smoothskinclusterweight'>smoothSkinClusterWeight plugin</a>.
    
Tyler Thornock for his <a href='http://www.charactersetup.com/tutorial_skinWeights.html'>tutorial</a> on a faster approach to get/set skin weights.


<br>
<b>Happy skinning :)</b>
