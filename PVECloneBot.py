#!/usr/bin/python3
# Token бота берется из системной переменной TG_CLONEBOT_TOKEN
# Разрешенные ChatID берется из системной переменной RES_CHATID, где они перечислены через запятую. 

import os, json, socket
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
ResolvedChatid = list(map(int, os.environ['RES_CHATID'].split(',')))

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
    PveSh = Conn.run('zfs list -t snapshot -o name | grep autosnap | grep ' + Dataset + ' | grep -v ' + ClonePostfix)
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
            #if ( ('sata' in key) or ('scsi' in key) ) and ( 'disk' in value):
            #print(value)
            if (('sata' in key) or ('scsi' in key)) and (('disk' in value) or ('cdrom' in value)):
                Disks[key]=value
    return(Disks)

def GetDiskNameSize(conf):
    #for cfg in conf.split(":")[1].split(","):
    Name = 'cdrom'
    Size = 'cdrom'
    for cfg in conf.split(","):
        if 'disk' in cfg:
            #print(cfg)
            Name = cfg
        if 'size' in cfg:
            #print(cfg)
            Size = cfg.split("=")[1]
    return(Name, Size)

def GetDataset(Node, Storage):
    Conn = SSHConnection(Node, login='root')
    PveSh = Conn.run('pvesh get storage/' + Storage + '/ --output-format json')
    PveSh = PveSh.stdout.decode("utf-8")
    Dataset = json.loads(PveSh)['pool']
    return(Dataset)

def CreateClone(Node, Snapshot):
    Conn = SSHConnection(Node, login='root')
    NewDataset = Snapshot.split("@")[0] + ClonePostfix
    Conn.run('zfs clone ' + Snapshot + ' ' + NewDataset)
    Conn.run('zfs set sync:label=' + ZfsLabel + ' ' + NewDataset)
    return(NewDataset)

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
    PveSh = Conn.run('pvesh set /nodes/' + CrTarget['Node'] + '/qemu/' + CrTarget['VMid'] + '/config/ -' + scsi + '=' + CrTarget['TgDisk'].split(":")[0] + ':' + CrTarget['TgDisk'].split(":")[1].split(",")[0] + '_tg-clone' + ',backup=0,replicate=0,discard=on')
    
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
        markup = types.ReplyKeyboardRemove(selective=False)
        Bot.send_message(message.chat.id, "Привет!", reply_markup=markup)
        # --------------- Вывод основных кнопок ---------------
        markup = types.InlineKeyboardMarkup()
        itembtn1 = types.InlineKeyboardButton(text='Сделать Клон', callback_data='create_clone')
        itembtn2 = types.InlineKeyboardButton(text='Список Клонов', callback_data='list_all_clone')
        itembtn3 = types.InlineKeyboardButton(text='Удалить Клон', callback_data='delete_clone')
        markup.add(itembtn1, itembtn2)
        markup.add(itembtn3)
        Bot.send_message(message.chat.id, "Выбери команду:", reply_markup=markup)

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

# --------------- Создание нового клона ---------------

# Накапливаем данные от обработчика к обработчику
CrTarget = {}
DelTarget = {}

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

@Bot.callback_query_handler(func = lambda call: call.data == "create_clone")
def CreateSelectNode(call):
    global CrTarget
    global Nodes
    Nodes = GetNodesList()
    #CrTarget['Cluster'] = call.data.split(":")[1]
    markup = types.InlineKeyboardMarkup()
    for NodeName in Nodes:
        markup.add(types.InlineKeyboardButton(text=NodeName, callback_data='create_clone_node:' + NodeName))
    Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите ноду:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_node")
def CreateSelectVMid(call):
    try:
        global CrTarget
        CrTarget['Node'] = call.data.split(":")[1]
        markup = types.InlineKeyboardMarkup()
        VMs=GetVMList(CrTarget['Node'])
        #Сортируем полученный список VM
        VMs.sort(key=lambda dictionary: dictionary['vmid'])
        for VM in VMs:
            markup.add(types.InlineKeyboardButton(text=str(VM['vmid']) + ' ' + VM['name'], callback_data='create_clone_vmid:' + str(VM['vmid'])))
        Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите VM:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_vmid")
def CreateSelectDisk(call):
    try:
        global CrTarget
        CrTarget['Disks'] = {}
        CrTarget['VMid'] = call.data.split(":")[1]
        markup = types.InlineKeyboardMarkup()
        Disks=GetVMDisks(CrTarget['Node'], CrTarget['VMid'])
        for port, conf in Disks.items():
            Name, Size = GetDiskNameSize(conf)
            if ClonePostfix not in Name:
                CrTarget['Disks'][port] = conf
                if  'cdrom' not in conf:
                    #print(conf)
                    markup.add(types.InlineKeyboardButton(text=Name + ' ' + Size, callback_data='create_clone_disk:' + Name))
        #print(CrTarget)
        Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите диск:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_disk")
def CreateSelectDay(call):
    try:
        global CrTarget
        CrTarget['TgDisk'] = []
        DiskName = call.data.split(":")[2]
        if DiskName in GetCloneList(CrTarget['Node']):
            Bot.send_message(call.from_user.id, 'Для выбранного диска уже есть клон, сначала нужно удалить его. Начните заново: /start')
        else:
            for port, conf in CrTarget['Disks'].items():
                if DiskName in conf:
                    CrTarget['TgDisk'] = conf
            markup = types.InlineKeyboardMarkup()
            CrTarget['TgDataset'] = GetDataset(CrTarget['Node'], CrTarget['TgDisk'].split(":")[0])
            CrTarget['Snapshots'] = GetVMSnapshot(CrTarget['Node'],  CrTarget['TgDataset'] + '/' + CrTarget['TgDisk'].split(":")[1].split(',')[0] )
            #print(CrTarget['Snapshots'])
            Days = []
            for Snapshot in CrTarget['Snapshots']:
                day = Snapshot.split("_")[1]
                if day not in Days:
                    Days.append(day)
            #print(Days)
            for day in Days:
                markup.add(types.InlineKeyboardButton(text=day, callback_data='create_clone_day:' + day))
            Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите день:', reply_markup=markup)
    except KeyError:
        ToStart(call)
    except IndexError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "create_clone_day")
def CreateSelectTime(call):
    try:
        global CrTarget
        CrTarget['Day'] = call.data.split(":")[1]
        Times = []
        for Snapshot in CrTarget['Snapshots']:
            Day = Snapshot.split("_")[1]
            Time = Snapshot.split("_")[2]
            if Day == CrTarget['Day']:
                Times.append(Time)
        markup = types.InlineKeyboardMarkup()
        i = 0
        row = []
        NewRow = {}
        st = 3
        for TimeIndx in range(len(Times)):
            i = TimeIndx +1
            #print(' i= ' + str(i))
            #print(Times[TimeIndx])
            if (i % st) == 0:
                #print(row)
                #print(i)
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
        Bot.send_message(call.from_user.id, '<b>Создание клона.</b> Выбирите Время:', reply_markup=markup)
    except KeyError:
        ToStart(call)

@Bot.callback_query_handler(func = lambda call: call.data.split("-")[0] == "create_clone_time")
def DoCreateClone(call):
    try:
        global CrTarget
        #Bot.answer_callback_query(callback_query_id=call.id, text='Я просто сообщение от бота, которое не останеться в истории переписки.', show_alert=True)
        CrTarget['Time'] = call.data.split("-")[1]
        TgSnapshot = ''
        for Snapshot in CrTarget['Snapshots']:
            if (CrTarget['Time'] in Snapshot) and (CrTarget['Day'] in Snapshot):
                TgSnapshot = Snapshot
        #print(TgSnapshot)
        NewDataset = CreateClone(CrTarget['Node'], TgSnapshot)
        #print(NewDataset)
        AddDisk(CrTarget)
        Bot.send_message(call.from_user.id, 'Клон за ' + CrTarget['Day'] + ' ' + CrTarget['Time'] + ' создан и подключен к ' + CrTarget['VMid'] + '. Вернутся в начало диалога: /start')
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
    global CrTarget
    global Nodes
    Nodes = GetNodesList()
    markup = types.InlineKeyboardMarkup()
    for NodeName in Nodes:
        markup.add(types.InlineKeyboardButton(text=NodeName, callback_data='del_clone_node:' + NodeName))
    Bot.send_message(call.from_user.id, '<b>Удаление клона.</b> Выбирите ноду:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "del_clone_node")
def DelSelectDisk(call):
    DelTarget['Node'] =  call.data.split(":")[1]
    DelTarget['Disks'] = {}
    Clones = GetCloneList(DelTarget['Node'])
    if str(Clones) == '':
        Bot.send_message(call.from_user.id, 'Клонов на <b>' + DelTarget['Node'] + '</b> не найдено. Выбирите другую ноду или начните сначала: /start')
    else:
        markup = types.InlineKeyboardMarkup()
        for Dataset in Clones.split('\n'):
            VMid = Dataset.split("/")[-1].split('-')[1]
            DelTarget['Disks'][VMid] = GetVMDisks(DelTarget['Node'], VMid)
            for port, conf in DelTarget['Disks'][VMid].items():
                if ClonePostfix in conf:
                    markup.add(types.InlineKeyboardButton(text=VMid + ' Диск: ' + port + '  -  ' + conf.split(',')[0], callback_data='del_clone_disk:' + VMid + ':' + port))
        Bot.send_message(call.from_user.id, '<b>Удаление клона.</b> Выбирите клон:', reply_markup=markup)

@Bot.callback_query_handler(func = lambda call: call.data.split(":")[0] == "del_clone_disk")
def ListClone(call):
    try:
        DelTarget['VMid'] =  call.data.split(":")[1]
        DelTarget['Port'] =  call.data.split(":")[2]
        for port, conf in DelTarget['Disks'][DelTarget['VMid']].items():
            if port == DelTarget['Port']:
                DelTarget['Disk'] = conf
        Bot.send_message(call.from_user.id, 'Отключение диска: ' + Delete(DelTarget['Node'], DelTarget['VMid'], DelTarget['Port']))
        UnusedDisks = GetVMDisks(DelTarget['Node'], DelTarget['VMid'], unused=True)
        for port, conf in UnusedDisks.items():
            if DelTarget['Disk'].split(":")[1].split(',')[0] in conf:
                Bot.send_message(call.from_user.id, 'Удаление диска: ' + Delete(DelTarget['Node'], DelTarget['VMid'], port) + '\n\nВернутся в начало: /start')
    except KeyError:
        ToStart(call)

Bot.polling()
