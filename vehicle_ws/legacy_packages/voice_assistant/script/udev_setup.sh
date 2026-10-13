#!/bin/bash

echo  'KERNEL=="ttyACM*", ATTRS{idVendor}=="1a86", ATTRS{idProduct}=="55d3", MODE:="0777", GROUP:="dialout",  SYMLINK+="voice_assistant"' >/etc/udev/rules.d/voice_assistant.rules

systemctl daemon-reload
service udev reload
sleep 1
service udev restart
