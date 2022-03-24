import asyncio
import logging
import queue
import threading
import uuid
from traceback import print_exc

import yaml
import hashlib
from ehforwarderbot.chat import PrivateChat
from pyqrcode import QRCode
from typing import Optional, Collection, BinaryIO, Dict, Any
from datetime import datetime

from ehforwarderbot import MsgType, Chat, Message, Status, coordinator
from wechatPc import WechatPc, WechatPcClient

from . import __version__ as version

from ehforwarderbot.channel import SlaveChannel
from ehforwarderbot.types import MessageID, ChatID, InstanceID
from ehforwarderbot import utils as efb_utils
from ehforwarderbot.exceptions import EFBException
from wechatPc.models.websocket import *
from cachetools import TTLCache

from .ChatMgr import ChatMgr
from .CustomTypes import EFBGroupChat, EFBPrivateChat, EFBGroupMember
from .MsgDecorator import efb_text_simple_wrapper
from .WechatPcMsgProcessor import MsgProcessor
from .utils import process_quote_text, download_file

TYPE_HANDLERS = {
    1: MsgProcessor.text_msg,
    3: MsgProcessor.image_msg
}


class WechatPcChannel(SlaveChannel):
    channel_name: str = "Wechat Pc Slave"
    channel_emoji: str = "💬🖥️"
    channel_id = "tedrolin.wechatPc"

    wechatPc: WechatPc
    client: WechatPcClient

    config: Dict[str, Any] = {}

    # info_list = TTLCache(maxsize=2, ttl=600)
    # info_dict = TTLCache(maxsize=2, ttl=600)

    info_list = {}
    info_dict = {}

    update_friend_event = threading.Event()
    async_update_friend_event = asyncio.Event()
    update_friend_lock = threading.Lock()
    async_update_friend_lock = asyncio.Lock()

    update_friend_queue = queue.Queue()

    __version__ = version.__version__

    logger: logging.Logger = logging.getLogger(
        "plugins.%s.WeChatPcChannel" % channel_id)

    supported_message_types = {MsgType.Text, MsgType.Sticker, MsgType.Image,
                                MsgType.Link, MsgType.Voice, MsgType.Animation}

    def __init__(self, instance_id: InstanceID = None):
        super().__init__(instance_id)

        self.load_config()
        if 'uri' not in self.config:
            raise EFBException("wechatPc uri not found in config")
        uri = self.config['uri']
        if 'APP_ID' in self.config and "APP_KEY" in self.config:
            ts = int(datetime.timestamp(datetime.now()) * 1000)
            sign = hashlib.sha256(f"app_id={self.config['APP_ID']}&timestamp={ts}&app_key{self.config['APP_KEY']}".encode())\
                .hexdigest()
            uri += f'?app_id={self.config["APP_ID"]}&timestamp={ts}&hash={sign}'
        self.wechatPc = WechatPc(uri)
        self.client = self.wechatPc.register_client("abcd")  # dummy id
        self.loop = asyncio.get_event_loop()
        self.isLogon = False

        connected_event = threading.Event()
        login_event = threading.Event()

        self.info_list['friend'] = []
        self.info_dict['friend'] = {}

        ChatMgr.slave_channel = self

        @self.client.add_handler(OPCODE_FRIEND_LIST)
        async def on_friend_list(msg: dict):
            self.logger.debug(f"on_friend_list: {msg}")
            if 'friendList' in msg:
                self.info_list['friend'] = msg['friendList']
            self.process_friend_info()
            self.update_friend_event.set()
            # self.async_update_friend_event.set()

        @self.client.add_handler(OPCODE_WECHAT_QRCODE)
        async def on_qr_code(msg: dict):
            if 'loginQrcode' in msg:
                qr_obj = QRCode(msg['loginQrcode'])
                qr = qr_obj.terminal()
                qr += "\n" + "If the QR code was not shown correctly, please generate the qrcode for the link\n" \
                             f"{msg['loginQrcode']}\n" \
                             "and then scan it with your Wechat Client"
                self.logger.log(99, qr)

        @self.client.add_handler(OPCODE_WECHAT_GET_LOGIN_STATUS)
        async def on_login_status_change(msg: dict):
            if 'loginStatus' in msg:
                if msg['loginStatus'] == 1:
                    self.logger.info("Login Success")
                    login_event.set()
                    self.isLogon = True
                elif msg['loginStatus'] == 0:
                    self.logger.info("Wechat Pc Account Logout")
                    self.isLogon = False

        @self.client.add_handler(OPCODE_MESSAGE_RECEIVE)
        async def on_msg_receive(msg: dict):
            if 'wxid' not in msg:
                return
            if msg.get('isOwner', 1) == 1:
                return
            username = await self.async_get_friend_info('username', msg['wxid'])
            if username is None:
                username = msg['wxid']
            remark_name = await self.async_get_friend_info('nickname', msg['wxid'])
            if remark_name is None:
                remark_name = msg['wxid']

            chat = None
            author = None

            if 'roomId' in msg and msg['roomId'] != '':
                group_name = await self.async_get_friend_info('username', msg['roomId'])
                group_remark_name = await self.async_get_friend_info('nickname', msg['roomId'])
                chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                    uid=msg['roomId'],
                    name=group_name or group_remark_name or msg['roomId']
                ))
                author = ChatMgr.build_efb_chat_as_member(chat, EFBGroupMember(
                    name=username,
                    alias=remark_name,
                    uid=msg['wxid']
                ))
            else:
                chat = ChatMgr.build_efb_chat_as_private(EFBPrivateChat(
                    uid=msg['wxid'],
                    name=remark_name,
                ))
                author = chat.other

            if 'msgType' in msg and msg['msgType'] in TYPE_HANDLERS:
                efb_msg = TYPE_HANDLERS[msg['msgType']](msg)
            else:
                efb_msg = efb_text_simple_wrapper(msg['content'])
            efb_msg.author = author
            efb_msg.chat = chat
            efb_msg.deliver_to = coordinator.master
            coordinator.send_message(efb_msg)

        async def cron_update_friends():
            while True:
                await asyncio.sleep(60 * 10)
                self.logger.debug("Start updating friends")
                await self.client.get_friend_list()

        def connect():
            nonlocal self
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.wechatPc.connect())
            connected_event.set()
            self.loop.create_task(self.wechatPc.run())
            self.loop.create_task(cron_update_friends())
            self.loop.run_forever()

        try:
            t = threading.Thread(target=connect)
            t.daemon = True
            t.start()
            # self.loop.run_until_complete(self.updater.run_task(shutdown_hook=self.shutdown_hook.wait))
        except:
            print_exc()

        connected_event.wait()
        asyncio.run_coroutine_threadsafe(self.client.open(), self.loop).result()
        login_event.wait()

    def load_config(self):
        """
        Load configuration from path specified by the framework.
        Configuration file is in YAML format.
        """
        config_path = efb_utils.get_config_path(self.channel_id)
        if not config_path.exists():
            return
        with config_path.open() as f:
            d = yaml.full_load(f)
            if not d:
                return
            self.config: Dict[str, Any] = d

    def get_chat_picture(self, chat: 'Chat') -> BinaryIO:
        url = self.get_friend_info('headUrl', chat.uid)
        if not url:
            url = "https://pic2.zhimg.com/50/v2-6afa72220d29f045c15217aa6b275808_720w.jpg"  # temp workaround
        return download_file(url)

    def get_chat(self, chat_uid: ChatID) -> 'Chat':
        if 'chat' not in self.info_list or not self.info_list['chat']:
            self.logger.debug("Chat list is empty. Fetching...")
            self.update_friend_info()
        for chat in self.info_list['chat']:
            if chat_uid == chat.uid:
                return chat
        return None

    def get_chats(self) -> Collection['Chat']:
        if 'chat' not in self.info_list or not self.info_list['chat']:
            self.logger.debug("Chat list is empty. Fetching...")
            self.update_friend_info()
        return self.info_list['chat']

    def send_message(self, msg: 'Message') -> 'Message':
        chat_uid = msg.chat.uid
        if msg.edit:
            pass  # todo

        if msg.type in [MsgType.Text, MsgType.Link]:
            if isinstance(msg.target, Message):  # Reply to message
                max_length = 50
                tgt_text = process_quote_text(msg.target.text, max_length)
                msg.text = "%s\n\n%s" % (tgt_text, msg.text)
                # self.iot_send_text_message(chat_type, chat_uid, msg.text
                asyncio.run_coroutine_threadsafe(self.client.at_room_member(
                    room_id=chat_uid,
                    wxid=msg.target.author.uid,
                    nickname=msg.target.author.name,
                    message=msg.text
                ), self.loop).result()
            else:
                asyncio.run_coroutine_threadsafe(self.client.send_text(
                    wxid=msg.chat.uid,
                    content=msg.text
                ), self.loop).result()
            msg.uid = str(uuid.uuid4())
            self.logger.debug('[%s] Sent as a text message. %s', msg.uid, msg.text)
        return msg

    def poll(self):
        pass

    def send_status(self, status: 'Status'):
        pass

    def stop_polling(self):
        pass

    def get_message_by_id(self, chat: 'Chat', msg_id: MessageID) -> Optional['Message']:
        pass

    def process_friend_info(self):
        self.info_dict['friend'] = {}
        self.info_dict['chat'] = {}
        self.info_list['chat'] = []
        # For the first iteration, we don't care about the group chat
        for friend in self.info_list['friend']:
            self.info_dict['friend'][friend['wxid']] = friend

            friend_name = friend.get('username', '')
            friend_remark = friend.get('nickname', '')

            if '@chatroom' not in friend['wxid']:
                new_entity = EFBPrivateChat(
                    uid=friend['wxid'],
                    name=friend_name,
                    alias=friend_remark
                )
                self.info_list['chat'].append(ChatMgr.build_efb_chat_as_private(new_entity))
                self.info_dict['chat'][friend['wxid']] = new_entity

        # For the second iteration, we check if there's a name given to a group
        # If not, we have to use member name as temp name
        for friend in self.info_list['friend']:
            group_name = friend.get('username', None)
            group_remark = friend.get('nickname', None)
            group_wxid_list: str = friend.get('roomWxidList', '')

            if '@chatroom' in friend['wxid']:
                if not group_name and not group_remark and friend.get('roomWxidList', ''):
                    wxids = group_wxid_list.split("^G")
                    if len(wxids) <= 1:
                        continue
                    group_name_arr = []
                    for wxid in wxids:
                        if wxid not in self.info_dict['friend']:
                            continue
                        contact = self.info_dict['friend'][wxid]
                        group_name_arr.append(contact['username'] or contact['nickname'])
                    group_name = '、'.join(group_name_arr)
                    self.info_dict['friend'][friend['wxid']]['nickname'] = group_name
                    new_entity = EFBGroupChat(
                        uid=friend['wxid'],
                        name=group_name or group_remark or friend['wxid']
                    )
                else:
                    new_entity = EFBGroupChat(
                        uid=friend['wxid'],
                        name=group_name or group_remark or friend['wxid']
                    )
                self.info_list['chat'].append(ChatMgr.build_efb_chat_as_group(new_entity))
                self.info_dict['chat'][friend['wxid']] = new_entity

    def update_friend_info(self):
        with self.update_friend_lock:
            if 'friend' in self.info_list and self.info_list['friend']:
                return
            self.logger.debug('Updating friend info...')
            self.update_friend_event.clear()
            asyncio.run_coroutine_threadsafe(self.client.get_friend_list(), self.loop).result()
            self.update_friend_event.wait()
            self.logger.debug('Friend retrieved. Start processing...')
            self.process_friend_info()
            self.update_friend_event.clear()

    async def async_update_friend_info(self):
        async with self.async_update_friend_lock:
            if 'friend' in self.info_list and self.info_list['friend']:
                return
            self.logger.debug('Updating friend info...')
            self.async_update_friend_event.clear()
            await self.client.get_friend_list()
            self.logger.debug('Friend retrieved. Start processing...')
            await self.async_update_friend_event.wait()
            self.process_friend_info()
            self.async_update_friend_event.clear()

    async def async_get_chat_info(self, wechat_id: int) -> Union[None, Chat]:
        # logging.getLogger(__name__).info('async_get_friend_remark called')
        count = 0
        while count <= 1:
            if not self.info_dict.get('chat', None):
                await self.async_update_friend_info()
                count += 1
            else:
                break
        if count > 1:  # Failure or friend not found
            raise Exception("Failed to update friend list!")  # todo Optimize error handling
        # logging.getLogger(__name__).info('async_get_friend_remark returned')
        if not self.info_dict.get('chat', None) or wechat_id not in self.info_dict['chat']:
            return None
        return self.info_dict['chat'][wechat_id]

    def get_friend_info(self, item: str, wechat_id: int) -> Union[None, str]:
        # logging.getLogger(__name__).info('async_get_friend_remark called')
        count = 0
        while count <= 1:
            if not self.info_dict.get('friend', None):
                self.update_friend_info()
                count += 1
            else:
                break
        if count > 1:  # Failure or friend not found
            raise Exception("Failed to update friend list!")  # todo Optimize error handling
        # logging.getLogger(__name__).info('async_get_friend_remark returned')
        if not self.info_dict.get('friend', None) or wechat_id not in self.info_dict['friend']:
            return None
        return self.info_dict['friend'][wechat_id].get(item, None)

    async def async_get_friend_info(self, item: str, wechat_id: int) -> Union[None, str]:
        # logging.getLogger(__name__).info('async_get_friend_remark called')
        # count = 0
        # while count <= 1:
        #     if not self.info_dict.get('friend', None):
        #         await self.async_update_friend_info()
        #         count += 1
        #     else:
        #         break
        # if count > 1:  # Failure or friend not found
        #     raise Exception("Failed to update friend list!")  # todo Optimize error handling
        # logging.getLogger(__name__).info('async_get_friend_remark returned')
        if not self.info_dict.get('friend', None) or wechat_id not in self.info_dict['friend']:
            return None
        return self.info_dict['friend'][wechat_id].get(item, None)
