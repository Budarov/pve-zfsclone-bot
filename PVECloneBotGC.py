#!/usr/bin/python3
#Как пользоватся:
#-delta <часы> - Через какое время удалять датасет
#-add_cron - добавит скрипт в cron на ежедневное выполнение в 21:00 с параметрами -delta 96

import sys, datetime, os, subprocess, socket

try:
    import requests
except ModuleNotFoundError:
    os.system('python3 -m pip -q install requests > /dev/null') 
    import requests

# Добавляем задание в крон
def add_cron():
    try:
        from crontab import CronTab
    except ModuleNotFoundError:
        os.system('python3 -m pip -q install python-crontab > /dev/null') 
        from crontab import CronTab

    cron = CronTab(user='root')
    fname = os.path.basename(sys.argv[0])
    for job in cron:
        if fname in str(job):
            sys.exit('Task already has been added to crontab: ' + str(job))
    job = cron.new(command=sys.path[0]+'/'+fname+' -delta 96')
    job.hour.on(21)
    job.minute.on(0)
    cron.write()
    sys.exit('Task has been added to crontab: ' + str(job))

# Проверка входных аргументов
def check_args():
    args = sys.argv
    args.append('poof')
    if len(args) > 2:
        for arg, next_arg in zip(args[1::], args[2::]):
            if arg == "-delta":
                try:
                    delta_time = int(next_arg)
                except ValueError:
                    sys.exit('Use PVECloneBotGC.py -delta <difference in hours>')
            if arg == '-add_cron':
                add_cron()
    return(delta_time * 3600)


# Получаем список датасетов
def GetDatasets(PostFix):
    cmd ='zfs list -o name'
    cmd2 = 'grep ' + PostFix
    list = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE)
    try:
        output = subprocess.check_output(cmd2.split(), stdin=list.stdout)
    except  subprocess.CalledProcessError:
        return([])
    output = output.decode('utf-8').splitlines()
    return(output)

# Удаляем старые датасеты
def DelDatasets(Datasets, DeltaTime, ChekClone = False):
    Now = datetime.datetime.now()
    for Dataset in Datasets:
        DatasetTime = datetime.datetime(int(Dataset.split('_')[2].split('-')[2]), int(Dataset.split('_')[2].split('-')[1]), int(Dataset.split('_')[2].split('-')[0]), int(Dataset.split('_')[3].split(':')[0]), int(Dataset.split('_')[3].split(':')[1]), int(Dataset.split('_')[3].split(':')[2]))
        Delta = Now - DatasetTime
        Delta = Delta.seconds + (Delta.days * 86400)
        if Delta > DeltaTime:
            if not ChekClone:  
                cmd = 'zfs get origin -H -o value ' + Dataset
                output = subprocess.check_output(cmd.split())
                output = output.decode('utf-8')
                if (output != '-') and ('autosnap' in output):
                    cmd ='zfs destroy -r ' + Dataset
                    try:
                        subprocess.check_output(cmd.split(), stderr=subprocess.STDOUT)
                    except subprocess.CalledProcessError as err:
                        requests.post(url='https://api.telegram.org/bot' + os.environ['TG_TOKEN'] + '/sendMessage?parse_mode=html&chat_id=' + os.environ['TG_CHAT'] + '&text=' + ' <b>' + socket.gethostname() + ': </b> \nZFS том <b>' + Dataset + '</b> должен был быть удален автоматически, но при удалении возникла ошибка:\n<code>' + err.output.decode('utf-8') + '</code>')
                else:
                    requests.post(url='https://api.telegram.org/bot' + os.environ['TG_TOKEN'] + '/sendMessage?parse_mode=html&chat_id=' + os.environ['TG_CHAT'] + '&text=' + ' <b>' + socket.gethostname() + ': </b> \nZFS том <b>' + Dataset + '</b> должен был быть удален автоматически, но он НЕ является клоном, либо является клоном не из снимка sanoid! \n<b>origin:</b> <code>' + output + '</code>')
            else:
                requests.post(url='https://api.telegram.org/bot' + os.environ['TG_TOKEN'] + '/sendMessage?parse_mode=html&chat_id=' + os.environ['TG_CHAT'] + '&text=' + ' <b>' + socket.gethostname() + ': </b> \nZFS клон <b>' + Dataset + '</b> создан через telegram bot и существует уже слишком долго. Нужно согласовать удаление.')


DeltaTime = check_args()
Datasets = GetDatasets('_tg-rollback')
if Datasets != []:
    DelDatasets(Datasets, DeltaTime)
Datasets = GetDatasets('_tg-clone')
if Datasets != []:
    DelDatasets(Datasets, DeltaTime, True)