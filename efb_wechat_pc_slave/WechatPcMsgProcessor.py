import re
import base64
import tempfile
from urllib.request import urlopen

from efb_wechat_pc_slave.MsgDecorator import efb_text_simple_wrapper, efb_image_wrapper


class MsgProcessor:
    # 文本消息
    @staticmethod
    def text_msg(msg: dict):
        msg = MsgProcessor.trans_emoji(msg)
        return efb_text_simple_wrapper(msg['content'])

    # 收到图文消息,收到文件
    @staticmethod
    def rich_msg(msg: dict):
        m = re.search(r'<title>(.*?)<\/title>', msg['content'], re.IGNORECASE)
        title = ''
        if m :
            title = m.group(1)
            title = title.replace('<![CDATA[', '')
            title = title.replace(']]>', '')
            title += "\n"

        des = ''
        m = re.search(r'<des>(.*?)<\/des>', msg['content'], re.S|re.M)
        # print(m)
        if m :
            des = m.group(1)
            des = des.replace('<![CDATA[', '')
            des = des.replace(']]>', '')
            des += "\n"

        url = ''
        m = re.search(r'<url>(.*?)<\/url>', msg['content'], re.S|re.M)
        # print(m)
        if m :
            url = m.group(1)
            url = url.replace('<![CDATA[', '')
            url = url.replace(']]>', '')

        m = re.search(r'<sourcedisplayname>(.*?)<\/sourcedisplayname>', msg['content'], re.IGNORECASE)
        sourcedisplayname = ''
        if m :
            sourcedisplayname = m.group(1)
            sourcedisplayname = sourcedisplayname.replace('<![CDATA[', '')
            sourcedisplayname = sourcedisplayname.replace(']]>', '')
            sourcedisplayname += "\n"

        return efb_text_simple_wrapper(title + des + sourcedisplayname + url)
        
    # 自定义动画表情
    @staticmethod
    def emojipic_msg(msg: dict):
        m = re.search(r'cdnurl\s?=\s?"(.*?)"', msg['content'])
        if m == None:
            m = re.search(r'thumburl\s?=\s?"(.*?)"', msg['content'])
        if m :
            try:
                print(m.group(1))
                
                file = tempfile.NamedTemporaryFile()
                with urlopen(m.group(1)) as response:
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

    # 语音消息提示
    @staticmethod
    def voice_msg(msg: dict):
        return efb_text_simple_wrapper("您有一条语音消息，请在微信客户端查看")

    # 转换微信emoji
    @staticmethod
    def trans_emoji(msg: dict):
        emojis = {'[翻白眼]': '\uD83D\uDE44',
                '[微笑]': '\uD83D\uDE42',
                '[撇嘴]': '\uD83D\uDE1F',
                '[色]': '\uD83D\uDE0D',
                '[发呆]': '\uD83D\uDE26',
                '[得意]': '\uD83D\uDE0E',
                '[流泪]': '\uD83D\uDE2D',
                '[害羞]': '\uD83D\uDE0A',
                '[闭嘴]': '\uD83E\uDD10',
                '[睡]': '\uD83D\uDE2A',
                '[大哭]': '\uD83D\uDE22',
                '[发怒]': '\uD83D\uDE21',
                '[调皮]': '\uD83D\uDE1B',
                '[呲牙]': '\uD83D\uDE01',
                '[惊讶]': '\uD83D\uDE32',
                '[难过]': '\uD83D\uDE41',
                '[冷汗]': '\uD83D\uDE30',
                '[抓狂]': '\uD83D\uDE2B',
                '[吐]': '\uD83E\uDD2E',
                '[偷笑]': '\uD83E\uDD2D',
                '[可爱]': '\uD83D\uDE0A',
                '[白眼]': '\uD83D\uDE44',
                '[傲慢]': '\uD83D\uDE15',
                '[饥饿]': '\uD83D\uDE0B',
                '[困]': '\uD83D\uDE2A',
                '[惊恐]': '\uD83D\uDE28',
                '[流汗]': '\uD83D\uDE13',
                '[憨笑]': '\uD83D\uDE00',
                '[悠闲]': '\uD83D\uDEAC',
                '[咒骂]': '\uD83E\uDD2C',
                '[嘘]': '\uD83E\uDD2B',
                '[晕]': '\uD83D\uDE35',
                '[折磨]': '\uD83D\uDE23',
                '[衰]': '\uD83D\uDE22',
                '[骷髅]': '\uD83D\uDC80',
                '[敲打]': '\uD83E\uDD15',
                '[再见]': '\uD83D\uDC4B',
                '[鼓掌]': '\uD83D\uDC4F',
                '[糗大了]': '\uD83D\uDE11',
                '[坏笑]': '\uD83D\uDE2C',
                '[左哼哼]': '\uD83D\uDE24',
                '[右哼哼]': '\uD83D\uDE24',
                '[哈欠]': '\uD83E\uDD71',
                '[委屈]': '\uD83D\uDE41',
                '[快哭了]': '\uD83D\uDE25',
                '[阴险]': '\uD83D\uDE0F',
                '[亲亲]': '\uD83D\uDE1A',
                '[吓]': '\uD83D\uDE31',
                '[可怜]': '\uD83E\uDD7A',
                '[菜刀]': '\uD83D\uDD2A',
                '[西瓜]': '\uD83C\uDF49',
                '[啤酒]': '\uD83C\uDF7A',
                '[篮球]': '\uD83C\uDFC0',
                '[乒乓]': '\uD83C\uDFD3',
                '[咖啡]': '\u2615',
                '[饭]': '\uD83C\uDF5A',
                '[猪头]': '\uD83D\uDC37',
                '[玫瑰]': '\uD83C\uDF39',
                '[凋谢]': '\uD83E\uDD40',
                '[示爱]': '\uD83D\uDC44',
                '[爱心]': '\u2764',
                '[心碎]': '\uD83D\uDC94',
                '[礼物]': '\uD83C\uDF81',
                '[闪电]': '\u26A1',
                '[炸弹]': '\uD83D\uDCA3',
                '[刀]': '\u2694',
                '[足球]': '\u26BD',
                '[便便]': '\uD83D\uDCA9',
                '[月亮]': '\uD83C\uDF19',
                '[太阳]': '\uD83C\uDF1E',
                '[礼物]': '\uD83C\uDF81',
                '[拥抱]': '\uD83E\uDD17',
                '[赞]': '\uD83D\uDC4D',
                '[踩]': '\uD83D\uDC4E',
                '[握手]': '\uD83E\uDD1D',
                '[胜利]': '\u270C',
                '[抱拳]': '\uD83D\uDE4F',
                '[拳头]': '\u270A',
                '[爱你]': '\uD83E\uDD1F',
                '[OK]': '\uD83D\uDC4C',
                '[爱情]': '\uD83D\uDC91',
                '[飞吻]': '\uD83D\uDE18',
                '[发抖]': '\uD83E\uDD76',
                '[怄火]': '\uD83D\uDE20',
                '[磕头]': '\uD83D\uDE47',
                '[挥手]': '\uD83D\uDC4B',
                '[街舞]': '\uD83D\uDC83',
                '[献吻]': '\uD83D\uDE17',
                '[发]': '\uD83C\uDC05',
                '[红包]': '\uD83E\uDDE7',
                '[耶]': '\u270C',
                '[皱眉]': '\uD83E\uDD7A',
                '[emm]': '\uD83D\uDE11',
                '[好的]': '\uD83D\uDC4C',
                '[天啊]': '\uD83D\uDE32',
                '[打脸]': '\uD83E\uDD15',
                '[汗]': '\uD83D\uDE13',
                '[强壮]': '\uD83D\uDCAA',
                '[鬼魂]': '\uD83D\uDC7B',
                '[吐舌]': '\uD83D\uDE1D',
                '[合十]': '\uD83D\uDE4F',
                '[礼物]': '\uD83C\uDF81',
                '[庆祝]': '\uD83C\uDF89',
                '[破涕为笑]': '\uD83D\uDE02',
                '[笑脸]': '\uD83D\uDE04',
                '[无语]': '\uD83D\uDE12',
                '[失望]': '\uD83D\uDE14',
                '[恐惧]': '\uD83D\uDE31',
                '[脸红]': '\uD83D\uDE33',
                '[哇]': '\uD83E\uDD29',
                '[旺柴]': '\uD83D\uDC36',
                '[瓢虫]': '\uD83D\uDC1E',
                '[奸笑]': '\uD83D\uDE3C',
                '[捂脸]': '\uD83E\uDD26',
                '[福]': '\uD83C\uDE60'}

        for emoji_key in emojis:
            msg['content'] = msg['content'].replace(emoji_key, emojis[emoji_key])

        return msg