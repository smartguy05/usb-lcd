Unicode True
!include "MUI2.nsh"
!include "LogicLib.nsh"

!define APP_NAME "USB LCD Dashboard"
; build-installer.sh passes -DAPP_VERSION from pyproject.toml, the single source.
!ifndef APP_VERSION
    !define APP_VERSION "0.12.3"
!endif
!define APP_PUBLISHER "USB LCD Dashboard"
!define APP_KEY "Software\USB LCD Dashboard"
!define UNINSTALL_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\USB LCD Dashboard"
!ifndef PAYLOAD
    !define PAYLOAD "payload"
!endif
!ifndef OUTPUT_FILE
    !define OUTPUT_FILE "/work/dist/USB-LCD-Dashboard-Setup-${APP_VERSION}.exe"
!endif

Name "${APP_NAME}"
OutFile "${OUTPUT_FILE}"
InstallDir "$LOCALAPPDATA\Programs\USB LCD Dashboard"
InstallDirRegKey HKCU "${APP_KEY}" "InstallDir"
; AppX requires a self-signed package certificate in LocalMachine\TrustedPeople.
; Elevation is used only for certificate trust; app files remain per-user.
RequestExecutionLevel admin
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show

VIProductVersion "${APP_VERSION}.0"
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

    ; Extract the entire new release beside the live installation first. NSIS
    ; extraction is not transactional: writing directly over $INSTDIR can leave
    ; a mixture of old and new files when one copy fails.
    RMDir /r "$INSTDIR.__new"
    SetOutPath "$INSTDIR.__new"
    ClearErrors
    File /r "${PAYLOAD}\*.*"
    ${If} ${Errors}
        SetOutPath "$TEMP"
        RMDir /r "$INSTDIR.__new"
        MessageBox MB_OK|MB_ICONSTOP "The new application files could not be staged. Your existing installation was not changed." /SD IDOK
        Abort
    ${EndIf}
    IfFileExists "$INSTDIR.__new\python.exe" 0 stage_incomplete
    IfFileExists "$INSTDIR.__new\pythonw.exe" 0 stage_incomplete
    IfFileExists "$INSTDIR.__new\python312._pth" 0 stage_incomplete
    IfFileExists "$INSTDIR.__new\Lib\site-packages\usb_lcd_dashboard\__init__.py" stage_ready
    stage_incomplete:
        SetOutPath "$TEMP"
        RMDir /r "$INSTDIR.__new"
        MessageBox MB_OK|MB_ICONSTOP "The staged application payload is incomplete. Your existing installation was not changed." /SD IDOK
        Abort
    stage_ready:
    ; SetOutPath also changes setup's process working directory. Windows cannot
    ; rename or remove a directory while setup itself has it as the CWD.
    SetOutPath "$TEMP"

    IfFileExists "$INSTDIR\python.exe" 0 runtime_stopped
        ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard shutdown'
        ; Give the daemon time to close native Pillow/USB modules before their
        ; files are replaced. Copying over a live embedded Python can otherwise
        ; leave a reinstall with a partial site-packages tree.
        Sleep 1500
    runtime_stopped:

    ; A persistent MCP server or a hook interpreter can outlive the display
    ; daemon and keep embedded Python files locked. Stop only processes whose
    ; executable lives under this exact application directory.
    IfFileExists "$INSTDIR\*.*" 0 installed_processes_stopped
    ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR.__new\stop-installed-processes.ps1" -InstallDir "$INSTDIR"' $0
    ${If} $0 != 0
        RMDir /r "$INSTDIR.__new"
        MessageBox MB_OK|MB_ICONSTOP "USB LCD Dashboard processes could not be stopped (exit code $0). The existing installation was not changed; close Codex and Claude Code, then run setup again." /SD IDOK
        Abort
    ${EndIf}
    installed_processes_stopped:

    ; Keep the previous tree intact until the staged release has successfully
    ; taken its place. If either rename fails, restore the old tree.
    RMDir /r "$INSTDIR.__old"
    ClearErrors
    IfFileExists "$INSTDIR\*.*" 0 old_moved
    Rename "$INSTDIR" "$INSTDIR.__old"
    ${If} ${Errors}
        RMDir /r "$INSTDIR.__new"
        MessageBox MB_OK|MB_ICONSTOP "The existing application is still in use and could not be upgraded. It was not changed; quit USB LCD Dashboard and run setup again." /SD IDOK
        Abort
    ${EndIf}
    old_moved:
    ; Use robocopy rather than NSIS CopyFiles: CopyFiles delegates to the shell
    ; and can report failure for a recursive directory tree even after copying
    ; part of it. Robocopy codes 0-7 are successful outcomes; 8+ are failures.
    ; The untouched old tree still provides rollback until validation passes.
    CreateDirectory "$INSTDIR"
    ExecWait 'robocopy.exe "$INSTDIR.__new" "$INSTDIR" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP' $0
    DetailPrint "Staged payload activation exit code: $0"
    ${If} $0 >= 8
        RMDir /r "$INSTDIR"
        Rename "$INSTDIR.__old" "$INSTDIR"
        RMDir /r "$INSTDIR.__new"
        MessageBox MB_OK|MB_ICONSTOP "The new application could not be activated (robocopy exit code $0). The previous installation was restored." /SD IDOK
        Abort
    ${EndIf}
    IfFileExists "$INSTDIR\python.exe" 0 activation_incomplete
    IfFileExists "$INSTDIR\pythonw.exe" 0 activation_incomplete
    IfFileExists "$INSTDIR\python312._pth" 0 activation_incomplete
    IfFileExists "$INSTDIR\Lib\site-packages\usb_lcd_dashboard\__init__.py" activation_ready
    activation_incomplete:
        RMDir /r "$INSTDIR"
        Rename "$INSTDIR.__old" "$INSTDIR"
        RMDir /r "$INSTDIR.__new"
        MessageBox MB_OK|MB_ICONSTOP "The activated application payload is incomplete. The previous installation was restored." /SD IDOK
        Abort
    activation_ready:
    RMDir /r "$INSTDIR.__new"

    SetOutPath "$INSTDIR"
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\register-identity.ps1" -ExternalLocation "$INSTDIR" -PackagePath "$INSTDIR\USB-LCD-Dashboard.Identity.msix" -CertificatePath "$INSTDIR\USB-LCD-Dashboard.Identity.cer"' $0
    DetailPrint "Package identity setup exit code: $0"
    ${If} $0 != 0
        ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\unregister-identity.ps1" -CertificatePath "$INSTDIR\USB-LCD-Dashboard.Identity.cer"'
        RMDir /r "$INSTDIR"
        Rename "$INSTDIR.__old" "$INSTDIR"
        IfFileExists "$INSTDIR\register-identity.ps1" 0 identity_rollback_done
        ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\register-identity.ps1" -ExternalLocation "$INSTDIR" -PackagePath "$INSTDIR\USB-LCD-Dashboard.Identity.msix" -CertificatePath "$INSTDIR\USB-LCD-Dashboard.Identity.cer"'
        identity_rollback_done:
        MessageBox MB_OK|MB_ICONSTOP "Windows notification identity setup failed. The previous installation was restored." /SD IDOK
        Abort
    ${EndIf}

    ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard install' $0
    DetailPrint "Setup helper exit code: $0"
    ${If} $0 != 0
        ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\unregister-identity.ps1" -CertificatePath "$INSTDIR\USB-LCD-Dashboard.Identity.cer"'
        RMDir /r "$INSTDIR"
        Rename "$INSTDIR.__old" "$INSTDIR"
        IfFileExists "$INSTDIR\register-identity.ps1" 0 setup_rollback_done
        ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\register-identity.ps1" -ExternalLocation "$INSTDIR" -PackagePath "$INSTDIR\USB-LCD-Dashboard.Identity.msix" -CertificatePath "$INSTDIR\USB-LCD-Dashboard.Identity.cer"'
        setup_rollback_done:
        MessageBox MB_OK|MB_ICONSTOP "Hook and configuration setup failed with exit code $0. The previous installation was restored." /SD IDOK
        Abort
    ${EndIf}
    IfFileExists "$LOCALAPPDATA\usb-lcd-dashboard\install-state.json" setup_ready
        MessageBox MB_OK|MB_ICONSTOP "Hook and configuration setup did not complete. The application files were installed, but setup could not be completed." /SD IDOK
        Abort
    setup_ready:
    RMDir /r "$INSTDIR.__old"

    CreateDirectory "$SMPROGRAMS\USB LCD Dashboard"
    SetOutPath "$INSTDIR"
    CreateShortCut "$SMSTARTUP\USB LCD Dashboard.lnk" "$INSTDIR\pythonw.exe" "-m usb_lcd_dashboard run" "$INSTDIR\pythonw.exe" 0 SW_SHOWMINIMIZED "" "Start the USB LCD dashboard at login"
    ; The same command as the Startup shortcut, on purpose: cli.py turns a
    ; second launch into an LCD reconnect request rather than a port-in-use
    ; failure, so this doubles as the way to restart or recover the dashboard.
    CreateShortCut "$SMPROGRAMS\USB LCD Dashboard\USB LCD Dashboard.lnk" "$INSTDIR\pythonw.exe" "-m usb_lcd_dashboard run" "$INSTDIR\pythonw.exe" 0 SW_SHOWMINIMIZED "" "Start or reconnect the USB LCD dashboard"
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

    ; This installer is elevated only to trust the AppX certificate. Launching
    ; the daemon directly would make it an elevated child, outside the normal
    ; Explorer/tray session. Ask Explorer to open the per-user startup shortcut
    ; so the dashboard runs with the desktop user's ordinary token.
    Exec 'explorer.exe "$SMSTARTUP\USB LCD Dashboard.lnk"'
SectionEnd

Section "Uninstall"
    SetShellVarContext current
    ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard shutdown'
    Sleep 500
    ExecWait '"$INSTDIR\python.exe" -m usb_lcd_dashboard uninstall'
    ExecWait 'powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$INSTDIR\unregister-identity.ps1" -CertificatePath "$INSTDIR\USB-LCD-Dashboard.Identity.cer"'

    Delete "$SMSTARTUP\USB LCD Dashboard.lnk"
    RMDir /r "$SMPROGRAMS\USB LCD Dashboard"
    DeleteRegKey HKCU "${UNINSTALL_KEY}"
    DeleteRegKey HKCU "${APP_KEY}"
    RMDir /r "$INSTDIR"
SectionEnd
