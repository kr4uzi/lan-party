<?php

return [
    "pxe" => [
        "http" => "http://\${next-server}/pxe"
    ],
    "windrv" => [
        "http" => "http://\${next-server}/windrv",
        "db" => "/srv/windrv/drivers.sqlite3"
    ],
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