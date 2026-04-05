<?php header("Content-Type: text/plain"); ?>
#!ipxe

menu Windows
<?php
$config = require "config.php";
$entries = $config["entries"];
$wimTypes = ["boot", "install"];
foreach ($config["entries"] as $win => &$cfg) {
    foreach ($wimTypes as $type) {
        $cfg["{$type}-driver-target"] = array();
    }
}

$warnings = [];
try {
    $db = new PDO("sqlite:" . $config["windrv"]["db"], null, null, [PDO::SQLITE_ATTR_OPEN_FLAGS => PDO::SQLITE_OPEN_READONLY]);
    $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
} catch (Exception $e) {
    array_push($warnings, "Database connection failed. {$e}");
    $db = null;
}

//
// driver detection
// note: no echos until "menu entry creation"
//
if ($db) {
    $hwids = array();
    $nics  = $_GET['nics'] ?? [];
    foreach ($nics as $nic) {
        $ven    = $nic['ven']    ?? '';
        $dev    = $nic['dev']    ?? '';
        $subven = $nic['subven'] ?? '';
        $subsys = $nic['subsys'] ?? '';
        $rev    = $nic['rev']    ?? '';
        if (empty($ven) || empty($dev)) {
            continue;
        }

        // https://learn.microsoft.com/windows-hardware/drivers/install/identifiers-for-pci-devices
        $ven = strtoupper($ven);
        $dev = strtoupper($dev);
        if (!empty($subsys) && !empty($subven)) {
            $subsys = strtoupper($subsys);
            $subven = strtoupper($subven);

            if (!empty($rev)) {
                $rev = strtoupper($rev);
                $hwids[] = "PCI\\VEN_{$ven}&DEV_{$dev}&SUBSYS_{$subsys}{$subven}&REV_{$rev}";
            }

            $hwids[] = "PCI\\VEN_{$ven}&DEV_{$dev}&SUBSYS_{$subsys}{$subven}";
        }

        $hwids[] = "PCI\\VEN_{$ven}&DEV_{$dev}";
    }

    $wimArchMap = [
        0  => 'ntx86',
        5  => 'ntarm',
        6  => 'ntia64',
        9  => 'ntamd64',
        12 => 'ntarm64',
    ];
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

            $guid = shell_exec("wimlib-imagex info " . escapeshellarg($wimFile) . " --header | grep 'GUID' | sed 's/.*=\s*//'");
            $guid = trim($guid);
            if (!$guid) {
                array_push($warnings, "Could not read {$wimFile}");
                continue;
            }

            $xmlRaw = shell_exec("wimlib-imagex info " . escapeshellarg($wimFile) . " --xml");
            if (!$xmlRaw) {
                array_push($warnings, "Could not read {$wimFile}");
                continue;
            }

            try {
                $xml = new SimpleXMLElement($xmlRaw);
                $versionInfo = $xml->IMAGE[0]->WINDOWS->VERSION;

                if (!$versionInfo) {
                    array_push($warnings, "Version metadata not found in {$wimFile}");
                    continue;
                }

                $major = (string)$versionInfo->MAJOR;
                $minor = (string)$versionInfo->MINOR;
                $build = (string)$versionInfo->BUILD;

                $wimArchId = (int)$xml->IMAGE[0]->WINDOWS->ARCH;
                $arch = $wimArchMap[$wimArchId] ?? '';
                if (empty($arch)) {
                    array_push($warnings, "Unknown architecture ({$wimArchId}) in $wimFile");
                    continue;
                }
            } catch (Exception $e) {
                array_push($warnings, "Error parsing $wimFile: " . $e->getMessage());
                continue;
            }

            foreach($hwids as $hwid) {
                $sql = "SELECT target.id as target_id, driver.container as container
                    FROM `target`
                    JOIN driver ON driver.id = target.driver
                    WHERE target.arch = :arch
                    AND target.hwid = :hwid
                    AND (driver.container = :container OR driver.container IS NULL)
                    AND (target.os_major = :major AND (
                            target.os_minor <= :minor AND (
                                target.os_build <= :build OR target.os_build IS NULL
                            ) OR target.os_minor IS NULL
                        ) OR target.os_major IS NULL
                    )
                    ORDER BY (driver.container IS NOT NULL) DESC,
                        target.os_major DESC, target.os_minor DESC, target.os_build DESC,
                        target.date DESC,
                        target.v_major DESC, target.v_minor DESC, target.v_patch DESC, target.v_build DESC
                    LIMIT 1";

                $stmt = $db->prepare($sql);
                $stmt->execute([
                    ':arch' => $arch,
                    ':major' => $major,
                    ':minor' => $minor,
                    ':build' => $build,
                    ':hwid'  => $hwid,
                    ':container' => $guid
                ]);
                $match = $stmt->fetch(PDO::FETCH_ASSOC);
                if ($match) {
                    $cfg["{$wimType}-driver-missing"] = false;

                    // if the driver is *not* found in the {boot|install}.wim add it to the initialization list
                    if ($match['container'] != $wimFile) {
                        $cfg["{$wimType}-driver-target"][] = $match['target_id'];
                    }

                    break;
                }
            }

            if ($cfg["{$wimType}-driver-missing"]) {
                $cfg['name'] .=  " (*{$wimType})";
            }
        }
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

echo("item win_exit <back>\n");

if ($bootDriverMissing || $installDriverMissing) {
    echo("item --gap -- -------------------- Info ------------------\n");
}

if ($bootDriverMissing) {
    echo("item --gap -- (*boot)    No Boot Network Driver found\n");
}

if ($installDriverMissing) {
    echo("item --gap -- (*install) No Install Network Driver found\n");
}

if (!empty($warnings)) {
    echo("item --gap -- -------------------- Warnings ------------------\n");
    foreach($warnings as $num => $warning) {
        echo("item --gap -- Warning #{$num}\n");
        foreach (preg_split('/\r\n|\r|\n/', $warning) as $line) {
            if ($line !== '') {
                echo("item --gap -- " . $line . "\n");
            }
        }
    }
}
?>
choose win_target && goto ${win_target}

:win_exit
exit

<?php

//
// windows configuration creation
//
foreach ($entries as $win => &$cfg) {
    echo(":win_{$win}\n");
    echo("kernel wimboot\n");
    echo("initrd BCD BCD\n");
    echo("initrd win/boot.sdi boot.sdi\n");
    echo("initrd -n boot.wim " . $config["pxe"]["http"] . "/" . $cfg["boot"] . " boot.wim\n");
    echo("initrd -n winpeshl.ini win/winpeshl.ini winpeshl.ini\n");

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

    echo("initrd -n ipxe-startnet.cmd " . $config["pxe"]["http"] . "/win/startnet.php?{$params} ipxe-startnet.cmd\n");
    echo("boot\n\n");
}
?>