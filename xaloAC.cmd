# xaloAC-x410m1s0
@echo off
setlocal
REM xaloAC launcher - works from any directory when xaloAC is on PATH
set "XALOAC_HOME=%~dp0"
py -3 "%XALOAC_HOME%xaloAC.py" %*
exit /b %ERRORLEVEL%