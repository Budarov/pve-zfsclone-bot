# pve-zfsclone-bot
nano /etc/systemd/system/PVECloneBot.service

#--------------------------------
[Unit]
Description=PVE Clone TG Bot
After=network.target

[Service]
EnvironmentFile=/etc/environment
ExecStart=/root/PVECloneBot/PVECloneBot.py
Restart=always
StartLimitInterval=0

[Install]
WantedBy=multi-user.target
#--------------------------------

systemctl enable PVECloneBot.service
systemctl start PVECloneBot.service
