pushd ..\..
set PYTHONPATH=%cd%
popd

"C:/Program Files/Autodesk/Maya2027/bin/mayapy" -m unittest discover -s . -v
pause