pushd ..\..
set PYTHONPATH=%cd%
popd

"C:/Program Files/Autodesk/Maya2018/bin/mayapy" -m unittest discover -s . -v
pause