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
            "init" => ["BCD" => "win11/BCD", "boot.sdi" => "win11/boot.sdi"],
            "boot" => "win11/boot.wim",
            "install" => "win11/tiny11pro.wim",
            "name" => "Windows 11 (Tiny Pro)"
        ],
        "win11" => [
            "init" => ["BCD" => "win11/BCD", "boot.sdi" => "win11/boot.sdi"],
            "boot" => "win11/boot.wim",
            "install" => "win11/install.wim",
            "name" => "Windows 11"
        ],
        "win7" => [
            "init" => ["BCD" => "win7/BCD", "boot.sdi" => "win7/boot.sdi"],
            "boot" => "win7/boot.wim",
            "install" => "win7/install.wim",
            "name" => "Windows 7",
            // Note: this is the signed (secure boot enabled!) file
            //       from Windows 7 ESU image
            "extra" => [
                "initrd win7/bootmgfw.efi bootmgfw.efi"
            ]
        ]
    ]
];
?>