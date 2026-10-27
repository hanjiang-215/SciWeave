@echo off
setlocal
set "DIR=%~dp0.."
set "DIR=%DIR:\=/%"
pushd "%DIR%" >nul
uv run --project "%DIR%" --env-file "%DIR%/.env" sciencepal %*
set "CODE=%ERRORLEVEL%"
popd >nul
exit /b %CODE%
