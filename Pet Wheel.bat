@echo off
py -3 "%~dp0pet_wheel.py" %*
if errorlevel 1 (
  echo.
  echo pet_wheel.py exited with an error. See the output above.
  pause
)
