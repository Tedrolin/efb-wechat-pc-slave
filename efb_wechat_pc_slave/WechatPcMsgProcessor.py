import re
import html
import tempfile
from lxml import etree
from urllib.request import urlopen

from efb_wechat_pc_slave.MsgDecorator import efb_text_simple_wrapper, efb_image_wrapper, efb_msgType49_xml_wrapper, efb_location_wrapper


class MsgProcessor:
    # 文本消息
    @staticmethod
    def text_msg(msg: dict):
        msg = MsgProcessor.trans_emoji(msg)
        return efb_text_simple_wrapper(msg['content'])

    # 自定义动画表情
    @staticmethod
    def emojipic_msg(msg: dict):
        m = re.search(r'cdnurl\s?=\s?"(.*?)"', msg['content'])
        if m == None:
            m = re.search(r'thumburl\s?=\s?"(.*?)"', msg['content'])
        if m :
            try:
                file = tempfile.NamedTemporaryFile()
                with urlopen(html.unescape(m.group(1))) as response:
                    data = response.read()
                    file.write(data)
                return efb_image_wrapper(file)
            except Exception as e:
                print(e)

    # 图片消息
    @staticmethod
    def image_msg(msg: dict):
        if 'imageFile' in msg and 'base64Content' in msg['imageFile']:
            try:
                file = tempfile.NamedTemporaryFile()
                with urlopen(msg['imageFile']['base64Content']) as response:
                    data = response.read()
                    file.write(data)
                return efb_image_wrapper(file)
            except Exception as e:
                print(e)
        return efb_text_simple_wrapper("Image received. Please check it on your phone.")

    # 富文本消息 公众号图文，小程序等
    @staticmethod
    def msgType49_xml_msg(msg: dict):
        return efb_msgType49_xml_wrapper(msg['content'])

    # 邮件消息
    @staticmethod
    def mail_msg(msg: dict):
        xml = etree.fromstring(msg['content'])
        subject = xml.xpath('string(/msg/pushmail/content/subject/text())')
        sender = xml.xpath('string(/msg/pushmail/content/sender/text())')
        waplink = xml.xpath('string(/msg/pushmail/waplink/text())')

        text = f'发件人: {sender}\n标题：{subject}\n地址:{waplink}'
        return efb_text_simple_wrapper(text)

    # 公众号推荐
    @staticmethod
    def mp_card_msg(msg: dict):
        xml = etree.fromstring(msg['content'])
        headimgurl = xml.xpath('string(/msg/@smallheadimgurl)')
        nickname = xml.xpath('string(/msg/@nickname)')
        certinfo = xml.xpath('string(/msg/@certinfo)')

        try:
            text = f"\n 公众号: {nickname}\n简介: {certinfo}"
            file = tempfile.NamedTemporaryFile()
            with urlopen(headimgurl) as response:
                data = response.read()
                file.write(data)
            return efb_image_wrapper(file, nickname, text)
        except Exception as e:
            print(e)

    # 语音消息提示
    @staticmethod
    def voice_msg(msg: dict):
        return efb_text_simple_wrapper("您有一条语音消息，请在微信客户端查看")

    # 视频消息提示
    @staticmethod
    def voideo_msg(msg: dict):
        return efb_text_simple_wrapper("您有一条视频消息，请在微信客户端查看")

    # 位置消息
    @staticmethod
    def location_msg(msg: dict):
        xml = etree.fromstring(msg['content'])
        latitude = xml.xpath('string(/msg/location/@x)')
        longitude = xml.xpath('string(/msg/location/@y)')
        text = xml.xpath('string(/msg/location/@poiname)')

        if latitude == "" or longitude == "":
            return efb_text_simple_wrapper("📌位置获取失败，请在微信客户端查看")

        return efb_location_wrapper(float(latitude), float(longitude), text)

    # 转换微信emoji
    @staticmethod
    def trans_emoji(msg: dict):
        emojis = {
            "[OK]": "👌",
            "[emm]": "😑",
            "[乒乓]": "🏓",
            "[亲亲]": "😚",
            "[便便]": "💩",
            "[偷笑]": "🤭",
            "[傲慢]": "😤",
            "[再见]": "👋",
            "[冷汗]": "😰",
            "[凋谢]": "🥀",
            "[刀]": "⚔",
            "[发]": "🀅",
            "[发呆]": "😦",
            "[发怒]": "😡",
            "[发抖]": "🥶",
            "[可怜]": "🥺",
            "[可爱]": "😊",
            "[右哼哼]": "😤",
            "[合十]": "🙏",
            "[吐]": "🤮",
            "[吐舌]": "😝",
            "[吓]": "😱",
            "[呲牙]": "😁",
            "[咒骂]": "🤬",
            "[咖啡]": "☕",
            "[哇]": "🤩",
            "[哈欠]": "🥱",
            "[啤酒]": "🍺",
            "[嘘]": "🤫",
            "[困]": "😪",
            "[坏笑]": "😬",
            "[大哭]": "😢",
            "[天啊]": "😲",
            "[太阳]": "🌞",
            "[失望]": "😔",
            "[奸笑]": "😼",
            "[好的]": "👌",
            "[委屈]": "🙁",
            "[害羞]": "😊",
            "[左哼哼]": "😤",
            "[庆祝]": "🎉",
            "[强壮]": "💪",
            "[得意]": "😎",
            "[微笑]": "🙂",
            "[心碎]": "💔",
            "[快哭了]": "😥",
            "[怄火]": "😠",
            "[恐惧]": "😱",
            "[悠闲]": "🚬",
            "[惊恐]": "😨",
            "[惊讶]": "😲",
            "[憨笑]": "😀",
            "[打脸]": "🤕",
            "[抓狂]": "😫",
            "[折磨]": "😣",
            "[抱拳]": "🙏",
            "[拥抱]": "🤗",
            "[拳头]": "✊",
            "[挥手]": "👋",
            "[捂脸]": "🤦",
            "[握手]": "🤝",
            "[撇嘴]": "😟",
            "[敲打]": "🤕",
            "[无语]": "😒",
            "[旺柴]": "🐶",
            "[晕]": "😵",
            "[月亮]": "🌙",
            "[汗]": "😓",
            "[流汗]": "😓",
            "[流泪]": "😭",
            "[炸弹]": "💣",
            "[爱你]": "🤟",
            "[爱心]": "❤",
            "[爱情]": "💑",
            "[猪头]": "🐷",
            "[献吻]": "😗",
            "[玫瑰]": "🌹",
            "[瓢虫]": "🐞",
            "[白眼]": "🙄",
            "[皱眉]": "🥺",
            "[睡]": "😪",
            "[破涕为笑]": "😂",
            "[磕头]": "🙇",
            "[示爱]": "👄",
            "[礼物]": "🎁",
            "[笑脸]": "😄",
            "[篮球]": "🏀",
            "[糗大了]": "😑",
            "[红包]": "🧧",
            "[翻白眼]": "🙄",
            "[耶]": "✌",
            "[胜利]": "✌",
            "[脸红]": "😳",
            "[色]": "😍",
            "[菜刀]": "🔪",
            "[街舞]": "💃",
            "[衰]": "😢",
            "[西瓜]": "🍉",
            "[调皮]": "😛",
            "[赞]": "👍",
            "[足球]": "⚽",
            "[踩]": "👎",
            "[闪电]": "⚡",
            "[闭嘴]": "🤐",
            "[阴险]": "😏",
            "[难过]": "🙁",
            "[飞吻]": "😘",
            "[饥饿]": "😋",
            "[饭]": "🍚",
            "[骷髅]": "💀",
            "[鬼魂]": "👻",
            "[鼓掌]": "👏",
            "[酷]": "😎",
            "[让我看看]": "🫣",
            "[强]": "👍🏻",
        }

        for emoji_key in emojis:
            msg['content'] = msg['content'].replace(emoji_key, emojis[emoji_key])
        return msg
