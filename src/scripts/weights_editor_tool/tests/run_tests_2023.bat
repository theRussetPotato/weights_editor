pushd ..\..
set PYTHONPATH=%cd%
popd

"C:/Program Files/Autodesk/Maya2023/bin/mayapy" -m unittest discover -s . -v
pause