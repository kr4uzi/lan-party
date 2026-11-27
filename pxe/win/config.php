<?php

return [
    "pxe" => [
        "http" => "http://\${next-server}/pxe/win"
    ],
    "windrv" => [
        // URL used by iPXE (which resolves ${next-server}) to download the drivers
        "http" => "http://\${next-server}/windrv",
        // URL of the windrv API used by menu.php and startnet.php on this server
        "api" => "http://127.0.0.1/windrv/api.php"
    ],
    // winlive boot service (442-liveboot-menu.md): uncomment once it runs, to show the live boot entry
    // "winlive" => [
    //     // URL used by iPXE
    //     "http" => "http://\${next-server}:8080",
    //     // URL used by menu.php on this server
    //     "api" => "http://127.0.0.1:8080",
    //     // TLS front end of the service (Apache ProxyPass, 442-liveboot-menu.md):
    //     // the login tries it first; "" = plain HTTP only (with a warning)
    //     "https" => "https://lan.krauzi.de/winlive"
    // ],
    "entries" => [
        "tiny11" => [
            "boot" => "win11/boot.wim",
            "install" => "win11/tiny11pro.wim",
            "name" => "Windows 11 (Tiny Pro)",
            "unattend" => "win11/win11standard.xml"
        ],
        "win11" => [
            "boot" => "win11/boot.wim",
            "install" => "win11/install.wim",
            "name" => "Windows 11",
            "unattend" => "win11/win11standard.xml"
        ],
        "win7" => [
            "boot" => "win7/boot_x86_64.wim",
            "install" => "win7/install.wim",
            "name" => "Windows 7",
            // Note: this is the signed (secure boot enabled!) file
            //       from Windows 7 ESU image
            "extra" => [
               "initrd -n bootmgfw.efi win7/bootmgfw.efi bootmgfw.efi",
            ],
            "unattend" => "win7/win7standard.xml"
        ]
    ]
];
?>