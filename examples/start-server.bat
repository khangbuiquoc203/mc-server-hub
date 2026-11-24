@echo off
REM Example only. Point MC Server Hub at your real server BAT.
REM Do not add "start". The Java process must stay a child of this file
REM so the hub can capture logs and stop the whole tree.
java -Xms2G -Xmx4G -jar server.jar nogui
pause
