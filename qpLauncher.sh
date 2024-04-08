#!/bin/sh
# qpLauncher.sh

### Follow instructions on https://www.instructables.com/Raspberry-Pi-Launch-Python-script-on-startup/ to add this script to Cron

### @reboot sh /home/pi/Desktop/qpLauncher.sh >/home/pi/logs/cronlog 2>&1

cd /
cd /home/pi/Desktop/QPClient_Final
sudo python qp_client_final.py
cd/
