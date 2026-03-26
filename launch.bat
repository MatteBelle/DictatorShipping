@echo off
where py >nul 2>&1 && (py "%~dp0launch.py" & goto :eof)
python "%~dp0launch.py"
