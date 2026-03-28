# What is this about?
The main purpose of this software is to provide dynamic network card driver injection on a iPXE / wimboot / WinPE setup.
In essence, the windrvscan.py parses a .inf file and stores (hardware-id, windows, file) tuples in a sqlite3 database.

The logic data layout is as follows:
- driver (root-path, inf-file)
- container (driver, container-name)
- target (driver, windows-version, driver-version, hardware-id)
- file (target, file)


# Initialization and Usage:
```sh
# sudo -s
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install packaging wininfparser
python3 windrvscan.py path/to/inf.inf
```
Note: The database will store relative or absolute paths depending on how the inf file was provided.

# Adding Builtin Drivers from WIMs
```sh
# export all integrated drivers
wimextract /srv/pxe/win11/boot.wim 1 /Windows/INF/*.inf --dest-dir=/srv/windrv/win11/boot

# windows uses UTF-16 encoding in which the files are also exported
find /srv/windrv/win11/boot -name "*.inf" -exec sh -c 'iconv -f UTF-16 -t UTF-8 "{}" > "{}.utf8" && mv "{}.utf8" "{}"' \;

# add all drivers to the database
find /srv/windrv/win11/boot -name "*.inf" | xargs -I {} python3 windrvscan.py "{}" -c "win11/boot.wim" -db /srv/windrv/drivers.sqlite3
```

# TODOs
- Implement support for "LayoutFile" (apparently only for the Version section and apparently only for Win2000 and WinXP)
- Add support for DOS kernel handling (Win98)
- Add primitve Driver Support:
  -> Manufacturer section must *not* be present
  -> DefaultInstall.nt{amd64,...} must be present
- Add Class Driver Support:
   -> Potentially no hardware IDs are available (currently only HW IDs are stored)

# References
## About model section parsing:
https://learn.microsoft.com/windows-hardware/drivers/install/creating-inf-files-for-multiple-platforms-and-operating-systems
On Windows Server 2003 Service Pack 1 (SP1) and later, INF files must decorate entries 
in the INF Models section with .ntia64, .ntarm, .ntarm64 or .ntamd64 platform extensions 
to specify non-x86 target operating system versions.

These platform extensions are not required in INF files for x86-based target 
operating system versions, but are strongly recommended. 
The same platform extension decoration or .nt platform extension is optional 
on all other sections that support platform extensions.

1. Windows checks for a section-name.nt<architecture> section and, if one exists, processes it.
   Windows checks for the .nt<architecture> extension in the INF file that is being processed 
   and in any included INF files (that is, any INF files that are included with Include entries).

2. If a section-name.nt<architecture> section does not exist, Windows checks for 
   a section-name.nt section in the INF file or any included INF files.
   If one exists, Windows processes the section-name.nt section.

3. If a section-name.nt section does not exist, Windows processes a section-name section 
   that does not include a platform extension.

## Include and Needs directives
Include=filename.inf[,filename2.inf]...
Specifies one or more additional system-supplied INF files that contain sections needed to install this device. If this entry is specified, usually so is a Needs entry.

Needs=inf-section-name[,inf-section-name]...
Specifies the named sections that must be processed during the installation of this device. Typically, such a named section is a DDInstall.Components section within a system-supplied INF file that is listed in an Include entry. However, it can be any section that is referenced within such a DDInstall.Components section of the included INF.

=> Used to include system-supplied INF files / sections, therefore not required to be stored in the database