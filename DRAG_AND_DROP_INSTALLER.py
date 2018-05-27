"""
Drag and drop this file into your viewport to run the installer.
"""

import sys
import os
import glob
import shutil
import traceback
import time
import maya.cmds as cmds


def onMayaDroppedPythonFile(arg):
    try:
        source_dir = os.path.dirname(__file__)
        source_path = os.path.normpath(os.path.join(source_dir, "scripts", "weights_editor_tool"))
        
        # Make sure this installer is relative to the main tool.
        script_path = os.path.join(source_path, "weights_editor.py")
        if not os.path.exists(script_path):
            raise RuntimeError, "Unable to find 'scripts/weights_editor.py' relative to this installer file."
        
        install_path = None
        
        home_dir = os.getenv("HOME")
        
        # Suggest to install in user's home path if it exists.
        if home_dir:
            install_path = os.path.normpath(os.path.join(home_dir, "maya", "scripts"))
            
            msg = ("The weights editor tool will be installed in a new folder here:\n"
                   "\n"
                   "{}\n"
                   "\n"
                   "Is this ok?".format(install_path))
            
            input = cmds.confirmDialog(title="Installation path", 
                                       message=msg, 
                                       icon="warning", 
                                       button=["OK", "Cancel", "No, let me pick another path!"], 
                                       cancelButton="Cancel", 
                                       dismissString="Cancel")
            
            if input == "Cancel":
                return
            elif input == "No, let me pick another path!":
                install_path = None
        
        # Open file picker to choose where to install to.
        if install_path is None:
            results = cmds.fileDialog2(fileMode=3, 
                                       okCaption="Install here", 
                                       caption="Pick a folder to install to")
            
            # Exit if it was cancelled.
            if not results:
                return
            
            install_path = os.path.normpath(results[0])
        
        # Check if install path is in Python's path.
        python_paths = [os.path.normpath(path) for path in sys.path]
        if install_path not in python_paths:
            msg = ("The install path '{}' isn't found in any of Python's paths (sys.path).\n\n"
                   "This means Python won't be able to find the tool and run it.\n"
                   "This can be set in your Maya.env or userSetup.py files."
                   "\n\n"
                   "Do you want to continue anyways?".format(install_path))
            
            input = cmds.confirmDialog(title="Warning!", 
                                       message=msg, 
                                       icon="warning", 
                                       button=["OK", "Cancel"], 
                                       cancelButton="Cancel", 
                                       dismissString="Cancel")
            
            if input == "Cancel":
                return
        
        # Remove directory if it already exists.
        tool_path = os.path.join(install_path, "weights_editor_tool")
        if os.path.exists(tool_path):
            # Give a warning first!
            msg = ("This folder already exists:\n"
                   "\n"
                   "{}\n"
                   "\n"
                   "Continue to overwrite it?".format(tool_path))
            
            input = cmds.confirmDialog(title="Warning!", 
                                       message=msg, 
                                       icon="warning", 
                                       button=["OK", "Cancel"], 
                                       cancelButton="Cancel", 
                                       dismissString="Cancel")
            
            if input == "Cancel":
                return
            
            shutil.rmtree(tool_path)
        
        # Windows may throw an 'access denied' exception doing a copytree right after a rmtree.
        # Forcing it a slight delay seems to solve it.
        time.sleep(1)
        
        # Copy tool's directory over.
        shutil.copytree(source_path, tool_path)
        
        # Display success!
        msg = ("The tool has been successfully installed!\n"
               "If you want to remove it then simply delete this folder:\n\n"
               "{}\n\n"
               "Run the tool from the script editor by executing the following:\n"
               "from weights_editor_tool import weights_editor\n"
               "weights_editor.run()".format(tool_path))
        
        # Check if shelves folder exists in user's preferences.
        maya_version = cmds.about(version=True)
        shelves_path = os.path.normpath(os.path.join(home_dir, "maya", maya_version, "prefs", "shelves"))
        
        tool_shelf_path = os.path.normpath(os.path.join(source_dir, "shelves", "shelf_CustomTools.mel"))
        
        # If it exists, add option to create a shelf button.
        if os.path.exists(shelves_path) and os.path.exists(tool_shelf_path):
            msg = ("{}\n\n"
                   "Do you also want to install a shelf button now for quick access?".format(msg))
            
            dialog_buttons = ["Yes", "No thanks"]
        else:
            dialog_buttons = ["OK"]
        
        input = cmds.confirmDialog(title="Success!", 
                                   message=msg, 
                                   button=dialog_buttons)
        
        # If user allows it, copy over shelf button.
        if input == "Yes":
            new_tool_shelf_path = os.path.join(shelves_path, "shelf_CustomTools.mel")
            shutil.copy2(tool_shelf_path, new_tool_shelf_path)
            
            msg = ("The shelf button has been added!\n"
                   "Maya will need to be restarted in order to see it.")
            
            input = cmds.confirmDialog(title="Success!", 
                                       message=msg, 
                                       button=["OK"])
    except Exception as e:
        print traceback.format_exc()
        
        # Display error message if an exception was raised.
        msg = ("{}\n"
               "\n"
               "If you need help or have questions please send an e-mail with subject "
               "'Weights editor installation' to jasonlabbe@gmail.com".format(e))
        
        cmds.confirmDialog(title="Installation has failed!", 
                           message=msg, 
                           icon="critical", 
                           button=["OK"])