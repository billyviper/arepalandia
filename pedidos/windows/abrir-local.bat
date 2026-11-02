@echo off
REM Abre la pantalla del local de Arepalandia en Chrome, en una ventana propia (se puede usar WhatsApp y la planilla al lado)
REM y con impresion directa (sin la ventana de "Imprimir") en la impresora predeterminada.
REM La impresora termica tiene que estar como PREDETERMINADA en Windows.
REM Para que arranque solo: Win+R, escribir  shell:startup  y copiar este archivo ahi.

set LINK=https://pedidos.CAMBIAR.com/local

set CHROME="%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist %CHROME% set CHROME="%LocalAppData%\Google\Chrome\Application\chrome.exe"

start "" %CHROME% --user-data-dir="%LocalAppData%\ArepalandiaLocal" --kiosk-printing --disable-print-preview --autoplay-policy=no-user-gesture-required --start-maximized --app=%LINK%
