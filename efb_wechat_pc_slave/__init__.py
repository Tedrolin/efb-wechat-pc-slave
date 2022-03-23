import asyncio
import logging
import threading
import uuid
from traceback import print_exc

import yaml
from ehforwarderbot.chat import PrivateChat
from pyqrcode import QRCode
from typing import Optional, Collection, BinaryIO, Dict, Any

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

    info_list = TTLCache(maxsize=2, ttl=600)
    info_dict = TTLCache(maxsize=2, ttl=600)

    update_friend_event = threading.Event()
    update_friend_lock = threading.Lock()

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
        self.wechatPc = WechatPc(self.config.get('uri', 'ws://127.0.0.1:5678'))
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
            if 'friendList' in msg:
                self.info_list['friend'] = msg['friendList']
            self.update_friend_event.set()

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
                chat = ChatMgr.build_efb_chat_as_group(EFBGroupChat(
                    uid=msg['roomId'],
                    name=remark_name
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

        def connect():
            nonlocal self
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.wechatPc.connect())
            connected_event.set()
            self.loop.create_task(self.wechatPc.run())
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
        self.update_friend_info()
        for chat in self.info_list['chat']:
            if chat_uid == chat.uid:
                return chat
        return None

    def get_chats(self) -> Collection['Chat']:
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

    def update_friend_info(self):
        if not self.update_friend_event.is_set():
            self.info_list['friend'] = asyncio.run_coroutine_threadsafe(self.client.get_friend_list(),
                                                                        self.loop).result()
        self.update_friend_event.wait()
        self.info_dict['friend'] = {}
        self.info_list['chat'] = []
        # For the first iteration, we don't care about the group chat
        for friend in self.info_list['friend']:
            self.info_dict['friend'][friend['wxid']] = friend

            friend_name = friend.get('username', None)
            friend_remark = friend.get('nickname', None)

            if '@chatroom' not in friend['wxid']:
                new_entity = EFBPrivateChat(
                    uid=friend['wxid'],
                    name=friend_name,
                    alias=friend_remark
                )
                self.info_list['chat'].append(ChatMgr.build_efb_chat_as_private(new_entity))

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
                    new_entity = EFBGroupChat(
                        uid=friend['wxid'],
                        name=group_name or group_remark
                    )
                else:
                    new_entity = EFBGroupChat(
                        uid=friend['wxid'],
                        name=group_name or group_remark
                    )
                self.info_list['chat'].append(ChatMgr.build_efb_chat_as_group(new_entity))
        self.update_friend_event.clear()



    async def async_update_friend_info(self):
        if not self.update_friend_event.is_set():
            self.info_list['friend'] = await self.client.get_friend_list()
        self.update_friend_event.wait()
        self.info_dict['friend'] = {}
        for friend in self.info_list['friend']:
            self.info_dict['friend'][friend['wxid']] = friend
        self.update_friend_event.clear()

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
        count = 0
        while count <= 1:
            if not self.info_dict.get('friend', None):
                await self.async_update_friend_info()
                count += 1
            else:
                break
        if count > 1:  # Failure or friend not found
            raise Exception("Failed to update friend list!")  # todo Optimize error handling
        # logging.getLogger(__name__).info('async_get_friend_remark returned')
        if not self.info_dict.get('friend', None) or wechat_id not in self.info_dict['friend']:
            return None
        return self.info_dict['friend'][wechat_id].get(item, None)
