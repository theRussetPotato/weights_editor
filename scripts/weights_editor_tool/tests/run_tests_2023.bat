pushd ..\..
set PYTHONPATH=%cd%
popd

"Z:/Program Files/Autodesk/Maya2023/bin/mayapy" -m unittest discover -s . -v
pause