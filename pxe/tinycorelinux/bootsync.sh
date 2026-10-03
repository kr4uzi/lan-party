#!/bin/sh

A=/usr/local/share/applications

rm -f "$A"/pcmanfm-desktop-pref.desktop "$A"/update-desktops.desktop \
      "$A"/libfm-pref-apps.desktop

if [ -f "$A"/pcmanfm.desktop ]; then
    sed 's/^Name=.*/Name=Files/' "$A"/pcmanfm.desktop > /tmp/pcmanfm.desktop &&
        mv -f /tmp/pcmanfm.desktop "$A"/pcmanfm.desktop
fi

mkdir -p /home/tc/Downloads /home/tc/.netsurf
echo "enable_javascript:1" > /home/tc/.netsurf/Choices

chown -R tc:staff /home/tc


/usr/bin/sethostname box
/opt/bootlocal.sh &

ntpd -q -p 10.10.0.1 &
