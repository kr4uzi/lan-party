#!/bin/sh
# netsurf in TinyCoreLinux 17.x requires the .netsurf directory
# the extension with onboot.lst is loaded before the home directory
# for the user tc actually exists
mkdir -p /home/tc/.netsurf
echo "enable_javascript:1" > /home/tc/.netsurf/Choices
chown -R tc:staff /home/tc/.netsurf