# PowerShell script to run unit tests for GUI
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir\..\
python -m unittest discover gui/test -v
