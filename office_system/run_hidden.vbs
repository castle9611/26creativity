Option Explicit

Dim shell, fso, root, pythonw, runner, logs, logFile, errFile, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

root = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = root & "\python\pythonw.exe"
runner = root & "\run.py"
logs = root & "\logs"

If Not fso.FolderExists(logs) Then
    fso.CreateFolder(logs)
End If

logFile = logs & "\server.log"
errFile = logs & "\server-error.log"

shell.CurrentDirectory = root
shell.Environment("PROCESS")("PATH") = root & "\python;" & root & "\python\DLLs;" & shell.Environment("PROCESS")("PATH")
shell.Environment("PROCESS")("PYTHONPATH") = root
shell.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8:backslashreplace"

cmd = "%COMSPEC% /c " & """" & """" & pythonw & """ """ & runner & """ 1>>""" & logFile & """ 2>>""" & errFile & """" & """"
shell.Run cmd, 0, False
