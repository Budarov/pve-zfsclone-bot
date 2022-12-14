#!/usr/bin/python3
# Token бота берется из системной переменной TG_CLONEBOT_TOKEN
# Разрешенные ChatID берется из системной переменной RES_CHATID, где они перечислены через запятую. 

import os, json, socket, datetime
try:
    import pip
except ModuleNotFoundError:
    os.system('apt-get install -y python3-pip > /dev/null')
try:
    import telebot
except ModuleNotFoundError:
    os.system('python3 -m pip -q install pyTelegramBotAPI > /dev/null') 
    import telebot
from telebot import types
try:
    from openssh_wrapper import SSHConnection
except ModuleNotFoundError:
    os.system('python3 -m pip -q install openssh_wrapper > /dev/null') 
    from openssh_wrapper import SSHConnection

Bot = telebot.TeleBot(os.environ['TG_CLONEBOT_TOKEN'], parse_mode='HTML')
ZfsLabel = 'tg-clone'
ClonePostfix = '_tg-clone'
RollbackPostfix = '_tg-rollback'
ResolvedChatid = list(map(int, os.environ['RES_CHATID'].split(',')))
CrTarget = {}
DelTarget = {}

def UserVerification (id, ResolvedChatid):
    if id in ResolvedChatid:
        return(True)
    else:
        Bot.send_message(id, "Hello! This is a private bot. Your chat id is not allowed. Your chat id: " + str(id))

#----------------Общие функции--------------

def GetNodesList():
    Conn = SSHConnection(socket.gethostname(), login='root')
    PveSh = Conn.run('pvesh get cluster/status --output-format json')
    PveSh = PveSh.stdout.decode("utf-8")
    js = json.loads(PveSh)
    Nodes = []
    for node in js:
        if node['type'] == 'node':
            Nodes.append(node['name'])
    Nodes.sort()
    return(Nodes)

def GetCloneList(node):
    global ZfsLabel
    Conn = SSHConnection(node, login='root')
    PveSh = Conn.run('zfs list -r -o name,sync:label | grep '+ ZfsLabel + ' | awk \'{print $1}\'')
    return(PveSh.stdout.decode("utf-8"))

def GetVMList(node):
    Conn = SSHConnection(node, login='root')
    PveSh = Conn.run('pvesh get nodes/'+ node +'/qemu --output-format json')
    PveSh = PveSh.stdout.decode("utf-8")
    js = json.loads(PveSh)
    return(js)

def GetVMSnapshot(Node, Dataset, grep = ''):
    Conn = SSHConnection(Node, login='root')
    # PveSh = Conn.run('zfs list -t snapshot -o name | grep autosnap | grep ' + Dataset + ' | grep -v ' + ClonePostfix + ' | grep -v :15: | grep -v :45:')
    PveSh = Conn.run('zfs list -t snapshot -o name | grep autosnap | grep ' + Dataset + ' | grep -v ' + ClonePostfix + ' | grep -v ' + RollbackPostfix)
    print('zfs list -t snapshot -o name | grep autosnap | grep ' + Dataset + ' | grep -v ' + ClonePostfix + ' | grep -v ' + RollbackPostfix)
    PveSh = PveSh.stdout.decode("utf-8").split()
    return(PveSh)

def GetVMDisks(Node, VMid, unused=False):
    Conn = SSHConnection(Node, login='root')
    PveSh = Conn.run('pvesh get nodes/'+ Node +'/qemu/' + VMid + '/config --output-format json')
    PveSh = PveSh.stdout.decode("utf-8")
    Config = json.loads(PveSh)
    Disks = {}
    if unused:
        for key, value in Config.items():
            if ('unused' in key) and ( 'disk' in value):
                Disks[key]=value
    else:
        for key, value in Config.items():
            if (('sata' in key) or ('scsi' in key)) and (('disk' in value) or ('cdrom' in value)):
                Disks[key]=value
    return(Disks)

def GetVMRunStatus(Node, VMid):
    Conn = SSHConnection(Node, login='root')
    PveSh = Conn.run('pvesh get nodes/'+ Node +'/qemu/' + VMid + '/status/current --output-format json')
    PveSh = PveSh.stdout.decode("utf-8")
    Status = json.loads(PveSh)
    return(Status['qmpstatus'])

def GetDiskNameSize(conf):
    #for cfg in conf.split(":")[1].split(","):
    Name = 'cdrom'
    Size = 'cdrom'
    for cfg in conf.split(","):
        if 'disk' in cfg:
            Name = cfg
        if 'size' in cfg:
            Size = cfg.split("=")[1]
    return(Name, Size)

def GetDataset(Node, Storage):
    Conn = SSHConnection(Node, login='root')
    PveSh = Conn.run('pvesh get storage/' + Storage + '/ --output-format json')
    PveSh = PveSh.stdout.decode("utf-8")
    Dataset = json.loads(PveSh)['pool']
    return(Dataset)

def CreateClone(Node, Snapshot):
    now = datetime.datetime.now()
    date = now.strftime("%d-%m-%Y_%H:%M:%S")
    Conn = SSHConnection(Node, login='root')
    NewDataset = Snapshot.split("@")[0] + ClonePostfix + '_' + date
    Conn.run('zfs clone ' + Snapshot + ' ' + NewDataset)
    Conn.run('zfs set sync:label=' + ZfsLabel + ' ' + NewDataset)
    return(NewDataset)

def ZFSRollback(Node, Snapshot):
    now = datetime.datetime.now()
    date = now.strftime("%d-%m-%Y_%H:%M:%S")
    Conn = SSHConnection(Node, login='root')
    global RollbackPostfix
    Dataset = Snapshot.split("@")[0]
    NewDataset = Dataset + RollbackPostfix + '_' + date
    NewSnapshot = NewDataset + '@' + Snapshot.split("@")[1]
    Conn.run('zfs rename ' + Dataset + ' ' + NewDataset)
    Conn.run('zfs clone ' + NewSnapshot + ' ' + Dataset)
    Conn.run('zfs set sync:label=' + date + RollbackPostfix + ' ' + NewDataset)
    Conn.run('zfs promote ' + Dataset)
    #return(NewDataset)

def AddDisk(CrTarget):
    Conn = SSHConnection(CrTarget['Node'], login='root')
    scsi = ''
    ScsiList = []
    for port, conf in CrTarget['Disks'].items():
        ScsiList.append(port) 
    for i in range(30):
        port = 'scsi' + str(i)
        if port not in ScsiList:
            scsi = port
            break 
    #PveSh = Conn.run('pvesh set /nodes/' + CrTarget['Node'] + '/qemu/' + CrTarget['VMid'] + '/config/ -' + scsi + '=' + CrTarget['TgDisk'].split(":")[0] + ':' + CrTarget['TgDisk'].split(":")[1].split(",")[0] + '_tg-clone' + ',backup=0,replicate=0,discard=on')
    PveSh = Conn.run('pvesh set /nodes/' + CrTarget['Node'] + '/qemu/' + CrTarget['VMid'] + '/config/ -' + scsi + '=' + CrTarget['TgDisk'].split(":")[0] + ':' +  CrTarget['NewDataset'].split('/')[-1] + ',backup=0,replicate=0,discard=on')
def Delete(Node, VMid, Port):
    Conn = SSHConnection(Node, login='root')
    PveSh = Conn.run('pvesh set /nodes/' + Node + '/qemu/' + VMid + '/config -delete ' + Port)
    return(PveSh.stdout.decode("utf-8"))

def ToStart(call):
    Bot.send_message(call.from_user.id, 'Контекст диалога потерян, начните сначала: /start')

# --------------- Обработчки ---------------

#------------------ /start------------------
#Получаем список нод
Nodes =[]

@Bot.message_handler(commands=['start'])
def start_command(message):
    if UserVerification(message.chat.id, ResolvedChatid):
        # Накапливаем данные от обработчика к обработчику
        global CrTarget
        CrTarget[message.chat.id] = {}
        global DelTarget
        DelTarget[message.chat.id] = {}
        markup = types.ReplyKeyboardRemove(selective=False)
        Bot.send_message(message.chat.id, "Привет!", reply_markup=markup)
        # --------------- Вывод основных кнопок клон диска ---------------
        markup = types.InlineKeyboardMarkup()
        itembtn1 = types.InlineKeyboardButton(text='Тонкий клон диска из ZFS снапшота', callback_data='create_clone')
        itembtn2 = types.InlineKeyboardButton(text='Список Клонов', callback_data='list_all_clone')
        itembtn3 = types.InlineKeyboardButton(text='Удалить Клон', callback_data='delete_clone')
        markup.add(itembtn1)
        markup.add(itembtn2, itembtn3)
        Bot.send_message(message.chat.id, "Клонирование диска VM из ZFS <b>снапшота</b> за выбранное время. Тонкий клон диска будет подключен к VM как SCSI диск для <b>файлового</b> восстановления:", reply_markup=markup)

        # --------------- Вывод основных кнопок откат диска ---------------
        markup = types.InlineKeyboardMarkup()
        itembtn1 = types.InlineKeyboardButton(text='Откат диска к выбранному времени', callback_data='create_clone:rollback')
        markup.add(itembtn1)
        Bot.send_message(message.chat.id, "Откат диска VM к ZFS снапшоту за выбранное время для восстановления <b>диска целиком</b>:", reply_markup=markup)

# --------------- Просмотр сужествующих клонов ---------------

# @Bot.callback_query_handler(func = lambda call: call.data == 'list_all_clone')
# def list_all_clone_command(call):
#     if UserVerification(call.from_user.id, ResolvedChatid):
#         markup = types.InlineKeyboardMarkup()
#         for key, value in ClasterList.items():
#             markup.add(types.InlineKeyboardButton(text=key, callback_data='list_clone_cluster:'+key))
#         Bot.send_message(call.from_user.id, 'Выбирите кластер:', reply_markup=markup)

# @Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "list_clone_cluster")
# def ListClone(call):
#     data = call.data.split(":")[1]
#     NoClone = True
#     for NodeName, NodeIp in ClasterList[data].items():
#         clone = GetCloneList(NodeIp)
#         if str(clone) != '':
#             msg = 'Клоны на <b>' + NodeName + ':</b>\n' + clone + '\n\nВернутся в начало: /start'
#             Bot.send_message(call.from_user.id, msg)
#             NoClone = False
#     if NoClone:
#         Bot.send_message(call.from_user.id, 'Клоны на <b>' + data + ':</b> не найдены. \n\nВернутся в начало: /start')

@Bot.callback_query_handler(func = lambda call: call.data == 'list_all_clone')
def ListClone(call):
    NoClone = True
    global Nodes
    Nodes = GetNodesList()
    for NodeName in Nodes:
        clone = GetCloneList(NodeName)
        if str(clone) != '':
            msg = 'Клоны на <b>' + NodeName + ':</b>\n' + clone + '\n\nВернутся в начало: /start'
            Bot.send_message(call.from_user.id, msg)
            NoClone = False
    if NoClone:
        Bot.send_message(call.from_user.id, 'Клоны <b>не найдены</b>. \n\nВернутся в начало: /start')

# --------------- Создание нового клона  и откат диска.---------------

# @Bot.callback_query_handler(func = lambda call: call.data == 'create_clone')
# def list_all_clone_command(call):
#     if UserVerification(call.from_user.id, ResolvedChatid):
#         markup = types.InlineKeyboardMarkup()
#         for key, value in ClasterList.items():
#             markup.add(types.InlineKeyboardButton(text=key, callback_data='create_clone_cluster:'+key))
#         Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите кластер:', reply_markup=markup)

# @Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_cluster")
# def CreateSelectNode(call):
#     global CrTarget
#     CrTarget['Cluster'] = call.data.split(":")[1]
#     markup = types.InlineKeyboardMarkup()
#     for NodeName, NodeIp in ClasterList[CrTarget['Cluster']].items():
#         markup.add(types.InlineKeyboardButton(text=NodeName, callback_data='create_clone_node:' + NodeName))
#     Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите ноду:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone")
def CreateSelectNode(call):
    try:
        global CrTarget
        global Nodes
        Nodes = GetNodesList()
        #CrTarget['Cluster'] = call.data.split(":")[1]
        if 'rollback' in call.data.split(":"):
            CrTarget[call.from_user.id]['rollback'] = True
            CrTarget[call.from_user.id]['msg'] = 'Откат диска.'
        else:
            CrTarget[call.from_user.id]['rollback'] = False
            CrTarget[call.from_user.id]['msg'] = 'Создание клона.'
        markup = types.InlineKeyboardMarkup()
        for NodeName in Nodes:
            markup.add(types.InlineKeyboardButton(text=NodeName, callback_data='create_clone_node:' + NodeName))
        Bot.send_message(call.from_user.id, '<b>' + CrTarget[call.from_user.id]['msg'] + '</b> Выбирите ноду:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_node")
def CreateSelectVMid(call):
    try:
        global CrTarget
        CrTarget[call.from_user.id]['Node'] = call.data.split(":")[1]
        markup = types.InlineKeyboardMarkup()
        VMs=GetVMList(CrTarget[call.from_user.id]['Node'])
        #Сортируем полученный список VM
        VMs.sort(key=lambda dictionary: dictionary['vmid'])
        for VM in VMs:
            markup.add(types.InlineKeyboardButton(text=str(VM['vmid']) + ' ' + VM['name'], callback_data='create_clone_vmid:' + str(VM['vmid'])))
        Bot.send_message(call.from_user.id, '<b>' + CrTarget[call.from_user.id]['msg'] + '</b> Выбирите VM:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_vmid")
def CreateSelectDisk(call):
    try:
        global CrTarget
        CrTarget[call.from_user.id]['Disks'] = {}
        CrTarget[call.from_user.id]['VMid'] = call.data.split(":")[1]
        #----Проверяем что VM выключена для rollback----
        if (CrTarget[call.from_user.id]['rollback'] == True) and GetVMRunStatus(CrTarget[call.from_user.id]['Node'], CrTarget[call.from_user.id]['VMid']) != 'stopped':
            Bot.send_message(call.from_user.id, 'VM ' + CrTarget[call.from_user.id]['VMid'] + ' запущена, необходимо выключить VM и начать заново: /start')
        else:
            markup = types.InlineKeyboardMarkup()
            Disks=GetVMDisks(CrTarget[call.from_user.id]['Node'], CrTarget[call.from_user.id]['VMid'])
            for port, conf in Disks.items():
                Name, Size = GetDiskNameSize(conf)
                if ClonePostfix not in Name:
                    CrTarget[call.from_user.id]['Disks'][port] = conf
                    if  'cdrom' not in conf:
                        markup.add(types.InlineKeyboardButton(text=Name + ' ' + Size, callback_data='create_clone_disk:' + Name))
            Bot.send_message(call.from_user.id, '<b>' + CrTarget[call.from_user.id]['msg'] + '</b> Выбирите диск:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_disk")
def CreateSelectDay(call):
    try:
        global CrTarget
        CrTarget[call.from_user.id]['TgDisk'] = []
        DiskName = call.data.split(":")[2]
        if DiskName in GetCloneList(CrTarget[call.from_user.id]['Node']):
            Bot.send_message(call.from_user.id, 'Для выбранного диска уже есть клон, сначала нужно удалить его. Начните заново: /start')
        else:
            for port, conf in CrTarget[call.from_user.id]['Disks'].items():
                if DiskName in conf:
                    CrTarget[call.from_user.id]['TgDisk'] = conf
            markup = types.InlineKeyboardMarkup()
            CrTarget[call.from_user.id]['TgDataset'] = GetDataset(CrTarget[call.from_user.id]['Node'], CrTarget[call.from_user.id]['TgDisk'].split(":")[0])
            CrTarget[call.from_user.id]['Snapshots'] = GetVMSnapshot(CrTarget[call.from_user.id]['Node'],  CrTarget[call.from_user.id]['TgDataset'] + '/' + CrTarget[call.from_user.id]['TgDisk'].split(":")[1].split(',')[0] )
            Days = []
            for Snapshot in CrTarget[call.from_user.id]['Snapshots']:
                day = Snapshot.split("_")[1]
                if day not in Days:
                    Days.append(day)
            for day in Days:
                markup.add(types.InlineKeyboardButton(text=day, callback_data='create_clone_day:' + day))
            Bot.send_message(call.from_user.id, '<b>' + CrTarget[call.from_user.id]['msg'] + '</b> Выбирите день:', reply_markup=markup)
    except KeyError:
        ToStart(call)
    except IndexError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_day")
def CreateSelectTime(call):
    try:
        global CrTarget
        CrTarget[call.from_user.id]['Day'] = call.data.split(":")[1]
        Times = []
        for Snapshot in CrTarget[call.from_user.id]['Snapshots']:
            Day = Snapshot.split("_")[1]
            Time = Snapshot.split("_")[2]
            if Day == CrTarget[call.from_user.id]['Day']:
                Times.append(Time)
        markup = types.InlineKeyboardMarkup()
        i = 0
        row = []
        NewRow = {}
        st = 3
        for TimeIndx in range(len(Times)):
            i = TimeIndx +1
            if (i % st) == 0:
                row.append(types.InlineKeyboardButton(text=Times[TimeIndx], callback_data='create_clone_time-' + Times[TimeIndx]))
                markup.add(row[0], row[1], row[2])
                row = []              
            else:
                row.append(types.InlineKeyboardButton(text=Times[TimeIndx], callback_data='create_clone_time-' + Times[TimeIndx]))
            if (i == len(Times)) and (i % st) != 0:
                for k in range(len(row)):
                    markup.add(row[k])             
        # for Time in Times:
        #     if i < st:
        #         row.append(types.InlineKeyboardButton(text=Time, callback_data='create_clone_time-' + Time))
        #         i = i + 1
        #     else:
        #         markup.add(row[0], row[1], row[2])
        #         row = []
        #         i = 0
            #markup.add(types.InlineKeyboardButton(text=Time, callback_data='create_clone_time-' + Time))
        Bot.send_message(call.from_user.id, '<b>' + CrTarget[call.from_user.id]['msg'] + '</b> Выбирите Время:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split("-")[0] == "create_clone_time")
def DoCreateClone(call):
    try:
        global CrTarget
        #Bot.answer_callback_query(callback_query_id=call.id, text='Я просто сообщение от бота, которое не останеться в истории переписки.', show_alert=True)
        CrTarget[call.from_user.id]['Time'] = call.data.split("-")[1]
        TgSnapshot = ''
        for Snapshot in CrTarget[call.from_user.id]['Snapshots']:
            if (CrTarget[call.from_user.id]['Time'] in Snapshot) and (CrTarget[call.from_user.id]['Day'] in Snapshot):
                TgSnapshot = Snapshot
        if CrTarget[call.from_user.id]['rollback'] == False:
            CrTarget[call.from_user.id]['NewDataset'] = CreateClone(CrTarget[call.from_user.id]['Node'], TgSnapshot)
            AddDisk(CrTarget[call.from_user.id])
            Bot.send_message(call.from_user.id, 'Клон за ' + CrTarget[call.from_user.id]['Day'] + ' ' + CrTarget[call.from_user.id]['Time'] + ' создан и подключен к ' + CrTarget[call.from_user.id]['VMid'] + '. Вернутся в начало диалога: /start')
        if CrTarget[call.from_user.id]['rollback'] == True:
            ZFSRollback(CrTarget[call.from_user.id]['Node'], TgSnapshot)
            Bot.send_message(call.from_user.id, 'Откат диска <b>'+ CrTarget[call.from_user.id]['TgDisk'] +'</b> на ' + CrTarget[call.from_user.id]['Day'] + ' ' + CrTarget[call.from_user.id]['Time'] + ' на VM <b>' + CrTarget[call.from_user.id]['VMid'] + '</b> успешно произведен. Вернутся в начало диалога: /start')
        CrTarget = {}
    except KeyError:
        ToStart(call)

# ------------------------- Удаление клона ----------------------------

# @Bot.callback_query_handler(func = lambda call: call.data == 'delete_clone')
# def DelCloneCommand(call):
#     if UserVerification(call.from_user.id, ResolvedChatid):
#         markup = types.InlineKeyboardMarkup()
#         for key, value in ClasterList.items():
#             markup.add(types.InlineKeyboardButton(text=key, callback_data='del_clone_cluster:'+key))
#         Bot.send_message(call.from_user.id, '<b>Удаление клона.</b> Выбирите кластер:', reply_markup=markup)

# @Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "del_clone_cluster")
# def DelSelectNode(call):
#     global CrTarget
#     CrTarget['Cluster'] = call.data.split(":")[1]
#     markup = types.InlineKeyboardMarkup()
#     for NodeName, NodeIp in ClasterList[CrTarget['Cluster']].items():
#         markup.add(types.InlineKeyboardButton(text=NodeName, callback_data='del_clone_node:' + NodeName))
#     Bot.send_message(call.from_user.id, '<b>Удаление клона.</b> Выбирите ноду:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call:  call.data == 'delete_clone')
def DelSelectNode(call):
    global DelTarget
    Nodes = GetNodesList()
    markup = types.InlineKeyboardMarkup()
    for NodeName in Nodes:
        markup.add(types.InlineKeyboardButton(text=NodeName, callback_data='del_clone_node:' + NodeName))
    Bot.send_message(call.from_user.id, '<b>Удаление клона.</b> Выбирите ноду:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "del_clone_node")
def DelSelectDisk(call):
    DelTarget[call.from_user.id]['Node'] =  call.data.split(":")[1]
    DelTarget[call.from_user.id]['Disks'] = {}
    Clones = GetCloneList(DelTarget[call.from_user.id]['Node'])
    if str(Clones) == '':
        Bot.send_message(call.from_user.id, 'Клонов на <b>' + DelTarget[call.from_user.id]['Node'] + '</b> не найдено. Выбирите другую ноду или начните сначала: /start')
    else:
        markup = types.InlineKeyboardMarkup()
        for Dataset in Clones.split('\n'):
            VMid = Dataset.split("/")[-1].split('-')[1]
            DelTarget[call.from_user.id]['Disks'][VMid] = GetVMDisks(DelTarget[call.from_user.id]['Node'], VMid)
            for port, conf in DelTarget[call.from_user.id]['Disks'][VMid].items():
                if ClonePostfix in conf:
                    markup.add(types.InlineKeyboardButton(text=VMid + ' Диск: ' + port + '  -  ' + conf.split(',')[0], callback_data='del_clone_disk:' + VMid + ':' + port))
        Bot.send_message(call.from_user.id, '<b>Удаление клона.</b> Выбирите клон:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "del_clone_disk")
def ListClone(call):
    try:
        DelTarget[call.from_user.id]['VMid'] =  call.data.split(":")[1]
        DelTarget[call.from_user.id]['Port'] =  call.data.split(":")[2]
        for port, conf in DelTarget[call.from_user.id]['Disks'][DelTarget[call.from_user.id]['VMid']].items():
            if port == DelTarget[call.from_user.id]['Port']:
                DelTarget[call.from_user.id]['Disk'] = conf
        Bot.send_message(call.from_user.id, 'Отключение диска: ' + Delete(DelTarget[call.from_user.id]['Node'], DelTarget[call.from_user.id]['VMid'], DelTarget[call.from_user.id]['Port']))
        UnusedDisks = GetVMDisks(DelTarget[call.from_user.id]['Node'], DelTarget[call.from_user.id]['VMid'], unused=True)
        for port, conf in UnusedDisks.items():
            if DelTarget[call.from_user.id]['Disk'].split(":")[1].split(',')[0] in conf:
                Bot.send_message(call.from_user.id, 'Удаление диска: ' + Delete(DelTarget[call.from_user.id]['Node'], DelTarget[call.from_user.id]['VMid'], port) + '\n\nВернутся в начало: /start')
    except KeyError:
        ToStart(call)

Bot.polling()
