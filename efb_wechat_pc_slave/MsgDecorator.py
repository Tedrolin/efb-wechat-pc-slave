from typing import Mapping, Tuple, Union, IO
import re
import magic
import html
import tempfile
import urllib.parse
from urllib.request import urlopen
from lxml import etree
from traceback import print_exc

from ehforwarderbot import MsgType, Chat
from ehforwarderbot.chat import ChatMember
from ehforwarderbot.message import Substitutions, Message, LinkAttribute, LocationAttribute

def efb_text_simple_wrapper(text: str, ats: Union[Mapping[Tuple[int, int], Union[Chat, ChatMember]], None] = None) -> Tuple[Message]:
    """
    A simple EFB message wrapper for plain text. Emojis are presented as is (plain text).
    :param text: The content of the message
    :param ats: The substitutions of at messages, must follow the Substitution format when not None
                [[begin_index, end_index], {Chat or ChatMember}]
    :return: EFB Message
    """
    efb_msg = Message(
        type=MsgType.Text,
        text=text
    )
    if ats:
        efb_msg.substitutions = Substitutions(ats)
    return (efb_msg,)


def efb_msgType49_xml_wrapper(text: str) -> Tuple[Message]:
    """
    处理msgType49消息 - 复合xml, xml 中 //appmsg/type 指示具体消息类型.
    /msg/appmsg/type
    已知：
    //appmsg/type = 5   : 链接（公众号文章）
    //appmsg/type = 6   : 文件 （收到文件的第二个提示【文件下载完成】)，也有可能 msgType = 10000 【【提示文件有风险】没有任何有用标识，无法判断是否与前面哪条消息有关联】
    //appmsg/type = 8   : 搜狗表情，暂时不支持发送
    //appmsg/type = 17  : 实时位置共享
    //appmsg/type = 19  : 转发聊天记录
    //appmsg/type = 21  : 微信运动点赞
    //appmsg/type = 33  : 微信小程序
    //appmsg/type = 51  : 当前微信版本不支持展示该内容，请升级至最新版本。
    //appmsg/type = 57  : 【感谢 @honus 提供样本 xml】引用(回复)消息，未细致研究哪个参数是被引用的消息 id
    //appmsg/type = 63  : 直播卡片
    //appmsg/type = 74  : 文件 (收到文件的第一个提示)

    :param text: The content of the message
    :return: EFB Message
    """

    xml = etree.fromstring(text)
    efb_msgs = []
    result_text = ""
    try:
        type = int(xml.xpath('/msg/appmsg/type/text()')[0])

        if type == 5:       # xml链接
            showtype = int(xml.xpath('/msg/appmsg/showtype/text()')[0])
            if showtype == 0:  # 消息对话中的(测试的是从公众号转发给好友, 不排除其他情况)
                title = url = des = thumburl = None  # 初始化
                try:
                    title = xml.xpath('/msg/appmsg/title/text()')[0]
                    url = xml.xpath('/msg/appmsg/url/text()')[0]
                    des = xml.xpath('/msg/appmsg/des/text()')[0]
                    thumburl = xml.xpath('/msg/appmsg/thumburl/text()')[0]

                    sourceusername = xml.xpath(
                        '/msg/appmsg/sourceusername/text()')[0]
                    sourcedisplayname = xml.xpath(
                        '/msg/appmsg/sourcedisplayname/text()')[0]
                    result_text += f"\n转发自公众号【{sourcedisplayname}(id: {sourceusername})】\n\n"
                except Exception as e:
                    print_exc()
                if title is not None and url is not None:
                    attribute = LinkAttribute(
                        title=title,
                        description=des,
                        url=url,
                        image=thumburl
                    )
                    efb_msg = Message(
                        attributes=attribute,
                        type=MsgType.Link,
                        text=result_text,
                        vendor_specific={"is_mp": True}
                    )
                    efb_msgs.append(efb_msg)
            elif showtype == 1:  # 公众号发的推送
                items = xml.xpath('//item')

                cover = None
                content = ""
                for item in items:
                    title = url = digest = None  # 初始化
                    try:
                        title = item.find("title").text
                        url = item.find("url").text
                        digest = item.find("digest").text
                        if cover is None:
                            cover = item.find("cover").text
                    except Exception as e:
                        print_exc()
                        continue

                    if title is None:
                        continue

                    if title:
                        title = html.escape(title)

                    if url:
                        url = urllib.parse.quote(url or "", safe="?=&#:/")
                        content += f'<a href="{url}">{title}</a>'
                    else:
                        content += f"{title}"
                    
                    if digest:
                        digest = html.escape(digest)
                        content += f"\n{digest}"

                    content += f"\n\n"

                try:
                    if cover:
                        cover = cover.replace('\n', '')
                        
                        content = f"\n{content}"
                        if len(content) >= 800:
                            content = re.sub(r'chksm=(.*?)#', '', content)

                        file = tempfile.NamedTemporaryFile()
                        with urlopen(cover) as response:
                            data = response.read()
                            file.write(data)
                        efb_msg = efb_image_wrapper(file, "", content)[0]
                    else:
                        efb_msg = efb_text_simple_wrapper(content)[0]
                except Exception as e:
                    print(e)
                    
                efb_msgs.append(efb_msg)
        elif type == 6:     # 收到文件的第二个提示【文件下载完成】
            title = xml.xpath('string(/msg/appmsg/title/text())')
            efb_msg = Message(
                type=MsgType.Text,
                text=f"接收到一个文件\n文件名: {title}\n请到微信客户端查看",
            )
            efb_msgs.append(efb_msg)
        elif type == 8:     # 搜狗表情，暂时不支持发送
            efb_msg = Message(
                type=MsgType.Text,
                text=f"接收到一个不支持的表情\n请到微信客户端查看",
            )
            efb_msgs.append(efb_msg)
        elif type == 21:    # 微信运动点赞
            title = xml.xpath('string(/msg/appmsg/title/text())')
            efb_msg = Message(
                type=MsgType.Text,
                text=f"🏃{title}",
            )
            efb_msgs.append(efb_msg)
        elif type == 33:    # 微信小程序
            weappname = xml.xpath('string(/msg/appmsg/des/text())')
            title = xml.xpath('string(/msg/appmsg/title/text())')
            weappicon = xml.xpath('string(/msg/appmsg/weappinfo/weappiconurl/text())')
            pagepath = xml.xpath('string(/msg/appmsg/weappinfo/pagepath/text())')
            username = xml.xpath('string(/msg/appmsg/weappinfo/username/text())')
            appid = xml.xpath('string(/msg/appmsg/weappinfo/appid/text())')

            try:
                text = f"小程序: {weappname}\n分享: {title}\n\nAppid: {appid}\nUsername: {username}\nPath: {pagepath}"
                file = tempfile.NamedTemporaryFile()
                with urlopen(weappicon) as response:
                    data = response.read()
                    file.write(data)
                efb_msg = efb_image_wrapper(file, weappname, text)[0]
            except Exception as e:
                print(e)
                
            efb_msgs.append(efb_msg)
        elif type == 51:    # 当前微信版本不支持展示该内容，请升级至最新版本。
            title = xml.xpath('string(/msg/appmsg/title/text())')

            nickname = xml.xpath('string(/msg/appmsg/finderFeed/nickname/text())')
            desc = xml.xpath('string(/msg/appmsg/finderFeed/desc/text())')
            cover = xml.xpath('string(/msg/appmsg/finderFeed/mediaList/media/coverUrl/text())')
            
            if cover:
                try:
                    text = f"视频号: {nickname}\n内容: {desc}\n"
                    file = tempfile.NamedTemporaryFile()
                    with urlopen(cover) as response:
                        data = response.read()
                        file.write(data)
                    efb_msg = efb_image_wrapper(file, weappname, text)[0]
                except Exception as e:
                    print(e)
            else:
                efb_msg = Message(
                    type=MsgType.Text,
                    text=title
                )
            efb_msgs.append(efb_msg)
        elif type == 57:    # 引用（回复）消息
            msg = xml.xpath('/msg/appmsg/title/text()')[0]
            refer_msgType = int(
                xml.xpath('/msg/appmsg/refermsg/type/text()')[0])  # 被引用消息类型
            # refer_fromusr = xml.xpath('/msg/appmsg/refermsg/fromusr/text()')[0] # 被引用消息所在房间
            # refer_fromusr = xml.xpath('/msg/appmsg/refermsg/chatusr/text()')[0] # 被引用消息发送人微信号
            refer_displayname = xml.xpath(
                '/msg/appmsg/refermsg/displayname/text()')[0]  # 被引用消息发送人微信名称
            refer_content = xml.xpath(
                '/msg/appmsg/refermsg/content/text()')[0]  # 被引用消息内容
            if refer_msgType == 1:  # 被引用的消息是文本
                result_text += f"「{refer_displayname}:\n{refer_content}」\n----------------\n{msg}"
            else:  # 被引用的消息非文本，提示不支持
                result_text += f"「{refer_displayname}:\n系统消息：被引用的消息不是文本，暂不支持展示」\n\n{msg}"
            efb_msg = Message(
                type=MsgType.Text,
                text=result_text,
                vendor_specific={"is_refer": True}
            )
            efb_msgs.append(efb_msg)
        elif type == 63:    # 直播卡片
            nickname = xml.xpath('string(/msg/appmsg/finderLive/nickname/text())')
            title = xml.xpath('string(/msg/appmsg/finderLive/desc/text())')
            cover = xml.xpath('string(/msg/appmsg/finderLive/media/coverUrl/text())')
            liveId = xml.xpath('string(/msg/appmsg/finderLive/finderLiveID/text())')

            try:
                text = f"视频号: {nickname}\n内容: {title}\nliveId: {liveId}"
                file = tempfile.NamedTemporaryFile()
                with urlopen(cover) as response:
                    data = response.read()
                    file.write(data)
                efb_msg = efb_image_wrapper(file, weappname, text)[0]
            except Exception as e:
                print(e)
                
            efb_msgs.append(efb_msg)
        elif type == 74:    # 收到文件的第一个提示
            pass
        else:
            efb_msg = Message(
                type=MsgType.Text,
                text=text
            )
            efb_msgs.append(efb_msg)
    except Exception as e:
        print_exc()
        efb_msg = Message(
            type=MsgType.Text,
            text=text
        )
        efb_msgs.append(efb_msg)

    return tuple(efb_msgs)


def efb_image_wrapper(file: IO, filename: str = None, text: str = None) -> Tuple[Message]:
    """
    A EFB message wrapper for images.
    :param file: The file handle
    :param filename: The actual filename
    :param text: The attached text
    :return: EFB Message
    """
    efb_msg = Message()
    efb_msg.file = file
    mime = magic.from_file(file.name, mime=True)
    if isinstance(mime, bytes):
        mime = mime.decode()

    if "gif" in mime:
        efb_msg.type = MsgType.Animation
    else:
        efb_msg.type = MsgType.Image

    if filename:
        efb_msg.filename = filename
    else:
        efb_msg.filename = file.name
        efb_msg.filename += '.' + \
            str(mime).split('/')[1]  # Add extension suffix

    if text:
        efb_msg.text = text

    efb_msg.path = efb_msg.file.name
    efb_msg.mime = mime
    return (efb_msg,)

# 位置消息
def efb_location_wrapper(latitude: float, longitude: float, text: None) -> Tuple[Message]:
    """
    A EFB message wrapper for images.
    :param latitude: latitude
    :param longitude: longitude
    :param text: The attached text
    :return: EFB Message
    """
    attribute = LocationAttribute(
        latitude=latitude,
        longitude=longitude,
    )
    efb_msg = Message(
        attributes=attribute,
        type=MsgType.Location,
        text=text,
    )

    return (efb_msg,)
