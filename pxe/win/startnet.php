<?php header("Content-Type: text/dos"); ?>
@echo off
setlocal enableextensions
TITLE Windows Setup Initialization...

<?php
function dieWithPause($message) {
  foreach (preg_split('/\r\n|\r|\n/', $message) as $line) {
      if ($line !== '') {
          echo("echo " . $line . "\r\n");
      }
  }

  die("pause\r\n");
}

$config = require 'config.php';

$installWim = $_GET['install-wim'] ?? '';
if (empty($installWim)) {
  dieWithPause("install-wim parameter is empty");
} else {
  $installWim = str_replace('/', '\\', $installWim);
}

// parse query string where params can appear multiple times
$queryString = $_SERVER['QUERY_STRING'] ?? '';
$pairs = array_filter(explode('&', $queryString));
$data = [];
foreach ($pairs as $pair) {
    list($key, $value) = explode('=', $pair);
    if (!isset($data[$key])) $data[$key] = array();
    array_push($data[$key], urldecode($value));
}

$bootTargets = $data["boot-driver-target"] ?? [];
$installTargets = $data["install-driver-target"] ?? [];
$targets = array_unique(array_merge($bootTargets, $installTargets));


$target2inf = [];
foreach ($targets as $target) {
  if (!isset($db)) {
    try {
      $db = new PDO("sqlite:" . $config["windrv"]["db"]);
      $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
    } catch (Exception $e) {
        dieWithPause("Database connection failed: {$e}");
    }
  }

  $stmt = $db->prepare(<<<SQL
    SELECT driver.inf as inf_file, target.root as root_path
    FROM `target`
    JOIN driver ON target.driver = driver.id
    WHERE `target`.id = :target
    LIMIT 1
  SQL);
  $stmt->execute([
      ':target' => $target
  ]);
  $match = $stmt->fetch(PDO::FETCH_ASSOC);
  if (!$match) {
    dieWithPause("Unknown Driver Target with ID={$target}");
  }

  $fileBase = "ipxe-driver-target-{$target}";
  echo("mkdir X:\\{$fileBase}\r\n");
  echo("expand {$fileBase}.cab -F:* X:\\{$fileBase} >nul\r\n");

  $inf = $match['root_path'];
  if ($inf == '.') $inf = '';
  else $inf .= '\\';
  $inf .= $match['inf_file'];
  $target2inf[$target] = "X:\\{$fileBase}\\$inf";
}

foreach ($bootTargets as $target) {
  echo("drvload {$target2inf[$target]} >nul\r\n");
}
?>

wpeinit

ping <?php echo($_SERVER['HTTP_HOST']); ?> /n 1 >nul 2>&1 || GOTO :NETWORKERROR

:: high performance mode
powercfg /s 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c

:: samba slow cleanup will cause the mount to fail (if using default configuration)
:: see README.md for fix
set /p="Mounting network drive ..." <nul

:MOUNTSMB
net use Y: \\<?php echo($_SERVER['HTTP_HOST']); ?>\pxe /USER:pxe pxe >nul 2>&1 && GOTO :INSTALL
set /p="." <nul
ping 127.0.0.1 -n 6 >nul
GOTO :MOUNTSMB

:: https://learn.microsoft.com/en-gb/windows-hardware/manufacture/desktop/windows-setup-command-line-options
:: - /InstallFrom needed to be be used with as below
:: - /InstallDrivers parameter wasn't accepted at all
:: - X:\setup.exe some check which displays a popup, therefore we use X:\sources\setup.exe

:INSTALL
echo.
X:\sources\setup.exe /noreboot /InstallFrom:Y:\<?php echo($installWim); ?> /Compact || GOTO :CLEANUP

:: if the setup was aborted do the cleanup
::SET EL=%ERRORLEVEL%
::IF %EL% NEQ 0 GOTO :CLEANUP

for /f "tokens=2 delims==" %%a in ('bcdedit /enum {default} ^| find "osdevice"') do set TARGETDRIVE=%%a
echo target %TARGETDRIVE%
if "%TARGETDRIVE%"=="" GOTO :INSTALLNOTFOUND

<?php
if (!empty($installTargets)) {
  echo("echo Installing driver(s) ...\r\n");

  foreach ($installTargets as $target) {
    echo("dism /Image:%TARGETDRIVE%:\ /Add-Driver:{$target2inf[$target]} >nul 2>&1\r\n");
  }
}
?>

:CLEANUP
echo Unmounting network drive ...
pause
net use Y: /delete >nul
goto :EOF

:INSTALLNOTFOUND
echo [!]
echo [!] ERROR: Unable to detect windows partition for automatic driver installation
echo [!] 
echo [!] Please manually install the driver:
echo [!] 1.) Make sure the partition is mounted:
echo [!]     diskpart > list disk > select disk ? > list volume > select volume ? > assign letter=?
echo [!] 2.) Copy the driver file from the network drive:
echo [!]     You can use notepad's "Open File" dialog to copy files
echo [!]     notepad > File > Open
echo [!]
echo [!] Enter EXIT or hit CTRL+C to exit
echo [!]
pause
cmd.exe
GOTO :CLEANUP

:NETWORKERROR
echo [!]
echo [!] ERROR: No Network Connection
echo [!] 
echo [!] No network drivers installed, not installed successfully or no network connection!
echo [!]
echo [!] Enter EXIT or hit CTRL+C to exit
echo [!]
pause
cmd.exe
GOTO :EOF