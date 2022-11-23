# pve-zfsclone-bot
nano /etc/systemd/system/PVECloneBot.service<br>
<br>
#--------------------------------<br>
[Unit]<br>
Description=PVE Clone TG Bot<br>
After=network.target<br>
<br>
[Service]<br>
EnvironmentFile=/etc/environment<br>
ExecStart=/root/PVECloneBot/PVECloneBot.py<br>
Restart=always<br>
StartLimitInterval=0<br>
<br>
[Install]<br>
WantedBy=multi-user.target<br>
#--------------------------------<br>
<br>
systemctl enable PVECloneBot.service<br>
systemctl start PVECloneBot.service<br>
