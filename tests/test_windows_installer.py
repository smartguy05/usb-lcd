from pathlib import Path


INSTALLER = Path(__file__).parents[1] / "packaging/windows/installer.nsi"
BUILD_SCRIPT = Path(__file__).parents[1] / "packaging/windows/build-installer.sh"
STOP_HELPER = Path(__file__).parents[1] / "packaging/windows/stop-installed-processes.ps1"


def test_windows_upgrade_stages_payload_before_touching_live_install() -> None:
    script = INSTALLER.read_text()

    stage = script.index('SetOutPath "$INSTDIR.__new"')
    extract = script.index('File /r "${PAYLOAD}\\*.*"')
    stop = script.index("usb_lcd_dashboard shutdown")
    move_old = script.index('Rename "$INSTDIR" "$INSTDIR.__old"')
    activate = script.index('ExecWait \'robocopy.exe "$INSTDIR.__new" "$INSTDIR"')
    leave_stage = script.index('SetOutPath "$TEMP"', extract)

    assert stage < extract < leave_stage < stop < move_old < activate


def test_windows_upgrade_validates_staged_runtime_and_application() -> None:
    script = INSTALLER.read_text()

    for required in (
        "$INSTDIR.__new\\python.exe",
        "$INSTDIR.__new\\pythonw.exe",
        "$INSTDIR.__new\\python312._pth",
        "$INSTDIR.__new\\Lib\\site-packages\\usb_lcd_dashboard\\__init__.py",
    ):
        assert required in script


def test_windows_upgrade_has_directory_swap_rollbacks() -> None:
    script = INSTALLER.read_text()

    assert script.count('Rename "$INSTDIR.__old" "$INSTDIR"') >= 3
    assert 'The previous installation was restored.' in script


def test_windows_upgrade_validates_activated_copy_before_deleting_stage() -> None:
    script = INSTALLER.read_text()

    copy = script.index('ExecWait \'robocopy.exe "$INSTDIR.__new" "$INSTDIR"')
    validate = script.index('IfFileExists "$INSTDIR\\python.exe"', copy)
    delete_stage = script.index('RMDir /r "$INSTDIR.__new"', validate)

    assert copy < validate < delete_stage


def test_windows_upgrade_accepts_robocopy_success_codes() -> None:
    script = INSTALLER.read_text()

    copy = script.index("robocopy.exe")
    failure_check = script.index("${If} $0 >= 8", copy)

    assert copy < failure_check
    assert "/E /COPY:DAT /DCOPY:DAT /R:2 /W:1" in script


def test_windows_upgrade_stops_only_processes_from_install_directory() -> None:
    installer = INSTALLER.read_text()
    helper = STOP_HELPER.read_text()
    build = BUILD_SCRIPT.read_text()

    assert '"$INSTDIR.__new\\stop-installed-processes.ps1" -InstallDir "$INSTDIR"' in installer
    assert 'cp "$PROJECT_DIR/packaging/windows/stop-installed-processes.ps1" "$PAYLOAD_DIR/"' in build
    assert "ExecutablePath" in helper
    assert "StartsWith($root" in helper
    assert "Stop-Process -Id $_.ProcessId" in helper


def test_start_menu_has_a_launcher_not_only_diagnostics() -> None:
    """The Start-menu folder must be able to start the dashboard.

    It once held only Diagnostics and Uninstall, so the only launcher lived in
    the Startup folder. Clicking the app in the Start menu ran `doctor`, which
    prints and exits under pythonw with no console and no tray icon -- the
    dashboard looked like it refused to come back after a quit. Both cli.py
    (which turns a second `run` into a reconnect request) and WINDOWS.md assume
    this shortcut exists.
    """
    script = INSTALLER.read_text()

    launcher = script.index(
        r'CreateShortCut "$SMPROGRAMS\USB LCD Dashboard\USB LCD Dashboard.lnk"'
    )
    assert "-m usb_lcd_dashboard run" in script[launcher : launcher + 300]
    assert "pythonw.exe" in script[launcher : launcher + 300]
