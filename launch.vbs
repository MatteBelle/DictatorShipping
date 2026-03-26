Set fso   = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
script = dir & "\launch.py"

' Try the Windows Python Launcher first (py.exe — always in PATH on Windows),
' then fall back to plain "python".
Dim launched : launched = False

On Error Resume Next
shell.Run "py """ & script & """", 0, False
If Err.Number = 0 Then launched = True
On Error GoTo 0

If Not launched Then
    shell.Run "python """ & script & """", 0, False
End If
