<?php header("Content-Type: text/plain"); ?>
#!ipxe

menu Windows
<?php
$config = require "config.php";
$entries = $config["entries"];
$wimTypes = ["boot", "install"];
foreach ($entries as $win => &$cfg) {
    foreach ($wimTypes as $type) {
        $cfg["{$type}-driver-target"] = array();
    }
}
unset($cfg);

require_once "windrv.php";

$warnings = [];

// A menu line iPXE shows as-is: " #" would start a comment and "${" a setting,
// so both are defused; long text is wrapped (iPXE drops leading spaces, so
// continuation lines cannot be indented).
function gap(string $text): void
{
    foreach (explode("\n", wordwrap($text, 72, "\n", true)) as $line) {
        $line = str_replace([" #", "\${"], [" ", "\$ {"], $line);
        echo("item --gap -- {$line}\n");
    }
}

//
// driver detection
// note: no echos until "menu entry creation"
//
// iPXE passes the PCI ids of the network adapters: nics[i][ven|dev|subven|subsys|rev|class]
$nics = array_filter($_GET['nics'] ?? [], fn($nic) => is_array($nic) && !empty($nic['ven']) && !empty($nic['dev']));
if (!empty($nics)) {
    foreach ($entries as $win => &$cfg) {
        if ($cfg["skip"] ?? false) continue;
        foreach ($wimTypes as $wimType) {
            $cfg["{$wimType}-driver-missing"] = true;

            $wimFile = $cfg[$wimType];
            if (!file_exists($wimFile)) {
                $cfg["skip"] = true;
                array_push($warnings, "{$wimFile} not found!");
                break;
            }

            $guid = shell_exec("wimlib-imagex info " . escapeshellarg($wimFile) . " --header | grep 'GUID' | sed 's/.*=\\s*//'");
            $guid = trim($guid ?? '');
            if (!$guid) {
                array_push($warnings, "Could not read {$wimFile}");
                continue;
            }

            // the WIM must have been scanned by windrvscan.py (its built-in drivers are the container)
            [$response, $error] = windrvApi($config, ["action" => "match", "container" => $guid, "nics" => array_values($nics)]);
            if ($error) {
                array_push($warnings, "{$wimFile}: {$error}");
                continue;
            }

            foreach ($response["nics"] as $nic) {
                if (isset($nic["error"])) {
                    array_push($warnings, "NIC {$nic['nic']}: {$nic['error']}");
                    continue;
                }
                // a network adapter is usable if the WIM has a driver or one can be injected
                if ($nic["covered"] || $nic["inject"]) {
                    $cfg["{$wimType}-driver-missing"] = false;
                }
                if ($nic["inject"]) {
                    $cfg["{$wimType}-driver-target"][] = $nic["driver"]["target"];
                }
            }
            $cfg["{$wimType}-driver-target"] = array_values(array_unique($cfg["{$wimType}-driver-target"]));

            if ($cfg["{$wimType}-driver-missing"]) {
                $cfg['name'] .=  " (*{$wimType})";
            }
        }
    }
    unset($cfg);
}

//
// live boot (442-liveboot-menu.md): ask the winlive boot service what this
// client's boot NIC gets (golden image, its model, onboarding, or why not)
//
$live = null;
// the NIC iPXE booted from: boot=<its mac>; unfiltered, without PCI ids the service keys it by MAC
$boot = current(array_filter($_GET['nics'] ?? [], fn($nic) => is_array($nic) && ($nic['mac'] ?? '') === ($_GET['boot'] ?? null)));
if (isset($config["winlive"]) && $boot) {
    $query = http_build_query([
        "mac" => $boot['mac'],
        "nic" => ($boot['ven'] ?? '') . ':' . ($boot['dev'] ?? ''),
        "busloc" => $boot['busloc'] ?? '',
    ]);
    $ctx = stream_context_create(["http" => ["timeout" => 2]]);
    $res = @file_get_contents($config["winlive"]["api"] . "/state?{$query}", false, $ctx);
    if ($res === false) {
        array_push($warnings, "winlive boot service not reachable");
    } else {
        $live = explode("\t", trim($res), 2) + [1 => ''];
    }
}

//
// menu entry creation
//
$numWin = 0;
$bootDriverMissing = false;
$installDriverMissing = false;
foreach ($entries as $win => &$cfg) {
    if ($cfg["skip"] ?? false) {
        continue;
    }

    if ($cfg["boot-driver-missing"] ?? false) $bootDriverMissing = true;
    if ($cfg["install-driver-missing"] ?? false) $installDriverMissing = true;

    $numWin++;
    echo("item win_{$win} {$cfg["name"]}\n");
}

if ($live) {
    // one entry: the login decides who may boot and who also manages the golden image
    [$what, $text] = $live;
    echo("item win_live Windows Live (login)\n");
    if (!in_array($what, ["golden", "model", "maintain", "install"])) {
        gap($text);
    }
}

echo("item win_exit <back>\n");

if ($bootDriverMissing || $installDriverMissing) {
    echo("item --gap --\n");
    echo("item --gap -- Info:\n");
    if ($bootDriverMissing) {
        gap("(*boot) no network driver for this machine in the boot image");
    }
    if ($installDriverMissing) {
        gap("(*install) no network driver for this machine in the install image");
    }
}

// entries sharing a WIM (tiny11 and win11: win11/boot.wim) report it once
$warnings = array_unique($warnings);
if (!empty($warnings)) {
    echo("item --gap --\n");
    echo("item --gap -- Warnings:\n");
    foreach ($warnings as $warning) {
        $lines = array_values(array_filter(preg_split('/\r\n|\r|\n/', $warning), fn($l) => trim($l) !== ''));
        foreach ($lines as $i => $line) {
            gap(($i ? "" : "! ") . $line);
        }
    }
}
?>
choose win_target && goto ${win_target}

:win_exit
exit

<?php if ($live):
    $http = $config["winlive"]["http"];
    $https = $config["winlive"]["https"] ?? "";
    $basic = fn($url) => str_replace("://", "://\${username:uristring}:\${password:uristring}@", $url);
?>
:win_live
login || exit
set wl-q mac=${mac:hexhyp}&nic=${pci/${busloc}.0x00.2}:${pci/${busloc}.0x02.2}&busloc=${busloc}
# POST form (not in any URL or access log) if this build has the params
# command; BIOS builds do not: HTTP Basic header instead. A chain uses up the
# parameter list, so it is built again right before each POST.
set wl-post 0
params --delete && params && set wl-post 1 ||
<?php if ($https): ?>
# BIOS builds of iPXE cannot do HTTPS
iseq ${platform} pcbios && goto win_live_http ||
iseq ${wl-post} 1 && goto win_live_https_post ||
chain --autofree <?= $basic($https) ?>/login?${wl-q} && exit || goto win_live_insecure
:win_live_https_post
params --delete && params && param user ${username} && param pass ${password} ||
chain --autofree <?= $https ?>/login?${wl-q}##params && exit || goto win_live_insecure
:win_live_insecure
echo
echo Secure login to <?= parse_url($https, PHP_URL_HOST) ?> failed (see the error above).
<?php endif; ?>
:win_live_http
echo
echo Logging in over plain HTTP sends the password UNENCRYPTED over the network.
prompt --key y Press y to log in anyway, any other key to cancel... || exit
iseq ${wl-post} 1 && goto win_live_http_post ||
chain --autofree <?= $basic($http) ?>/login?${wl-q} ||
exit
:win_live_http_post
params --delete && params && param user ${username} && param pass ${password} ||
chain --autofree <?= $http ?>/login?${wl-q}##params ||
exit

<?php endif; ?>
<?php

//
// windows configuration creation
//
foreach ($entries as $win => &$cfg) {
    echo(":win_{$win}\n");
    echo("kernel wimboot\n");
    echo("initrd BCD BCD\n");
    echo("initrd boot.sdi boot.sdi\n");
    echo("initrd -n boot.wim " . $config["pxe"]["http"] . "/" . $cfg["boot"] . " boot.wim\n");
    if (isset($cfg["winpeshl"])) {
        // custom winpeshl.ini (path relative to this directory), none if empty
        if (!empty($cfg["winpeshl"])) {
            echo("initrd -n winpeshl.ini " . $config["pxe"]["http"] . "/" . $cfg["winpeshl"] . " winpeshl.ini\n");
        }
    } else {
        echo("initrd winpeshl.ini winpeshl.ini\n");
    }

    $bootTargets = $cfg["boot-driver-target"] ?? [];
    $installTargets = $cfg["install-driver-target"] ?? [];
    $targets = array_unique(array_merge($bootTargets, $installTargets));
    foreach ($targets as $id) {
        $file = "ipxe-driver-target-{$id}.cab";
        echo("initrd -n {$file} " . $config["windrv"]["http"] . "/download.php?target={$id} {$file}\n");
    }

    $params = "install-wim=" . urlencode($cfg["install"]);
    if (isset($cfg["unattend"])) {
        $params .= "&unattend=" . urlencode($cfg["unattend"]);
    }

    foreach ($bootTargets as $id) {
        $params .= "&boot-driver-target={$id}";
    }
    foreach ($installTargets as $id) {
        $params .= "&install-driver-target={$id}";
    }

    foreach(($cfg["extra"] ?? []) as $extra) {
        echo("{$extra}\n");
    }

    echo("initrd -n ipxe-startnet.cmd " . $config["pxe"]["http"] . "/startnet.php?{$params} ipxe-startnet.cmd\n");
    echo("boot\n\n");
}
?>