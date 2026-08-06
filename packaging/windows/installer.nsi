Unicode True
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP_NAME "USB LCD Dashboard"
!define APP_VERSION "0.2.1"
!define APP_PUBLISHER "USB LCD Dashboard"
!define APP_KEY "Software\USB LCD Dashboard"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\USB LCD Dashboard"
!define PAYLOAD "payload"

Name "${APP_NAME}"
OutFile "/work/dist/USB-LCD-Dashboard-Setup-${APP_VERSION}.exe"
InstallDir "$LOCALAPPDATA\Programs\USB LCD Dashboard"
InstallDirRegKey HKCU "${APP_KEY}" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "0.2.1.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"
VIAddVersionKey "FileDescription" "Claude Code and Codex dashboard for Turing USB LCD"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "Copyright 2026 USB LCD Dashboard contributors"

!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_TITLE "USB LCD Dashboard is ready"
!define MUI_FINISHPAGE_TEXT "The dashboard is running. Plug in the 3.5-inch USB LCD and it will be detected automatically."
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function .onInit
    SetShellVarContext current
FunctionEnd

Function un.onInit
    SetShellVarContext current
FunctionEnd

Section "Install" SEC_MAIN
    SetShellVarContext current

    IfFileExists "$INSTDIR\python.exe" 0 runtime_stopped
        ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard shutdown'
        Sleep 500
    runtime_stopped:

    SetOutPath "$INSTDIR"
    File /r "${PAYLOAD}/*.*"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard install' $0
    DetailPrint "Setup helper exit code: $0"
    IfFileExists "$LOCALAPPDATA\usb-lcd-dashboard\install-state.json" setup_ready
        MessageBox MB_OK|MB_ICONSTOP "Hook and configuration setup did not complete. The application files were installed, but setup could not be completed." /SD IDOK
        Abort
    setup_ready:

    CreateDirectory "$SMPROGRAMS\USB LCD Dashboard"
    SetOutPath "$INSTDIR"
    CreateShortCut "$SMSTARTUP\USB LCD Dashboard.lnk" "$INSTDIR\pythonw.exe" "-m usb_lcd_dashboard run" "$INSTDIR\pythonw.exe" 0 SW_SHOWMINIMIZED "" "Start the USB LCD dashboard at login"
    CreateShortCut "$SMPROGRAMS\USB LCD Dashboard\Diagnostics.lnk" "$INSTDIR\python.exe" "-m usb_lcd_dashboard doctor" "$INSTDIR\python.exe" 0 SW_SHOWNORMAL "" "Check LCD, hooks, and autostart"
    CreateShortCut "$SMPROGRAMS\USB LCD Dashboard\Uninstall.lnk" "$INSTDIR\Uninstall.exe"

    WriteRegStr HKCU "${APP_KEY}" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${UNINSTALL_KEY}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKCU "${UNINSTALL_KEY}" "QuietUninstallString" '"$INSTDIR\Uninstall.exe" /S'
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${UNINSTALL_KEY}" "NoRepair" 1

    Exec '"$INSTDIR\pythonw.exe" -m usb_lcd_dashboard run'
SectionEnd

Section "Uninstall"
    SetShellVarContext current
    ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard shutdown'
    Sleep 500
    ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard uninstall'

    Delete "$SMSTARTUP\USB LCD Dashboard.lnk"
    RMDir /r "$SMPROGRAMS\USB LCD Dashboard"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    DeleteRegKey HKCU "${APP_KEY}"
    RMDir /r "$INSTDIR"
SectionEnd
