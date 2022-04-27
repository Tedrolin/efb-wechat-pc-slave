import hashlib
import base64
import os
from traceback import print_exc
import requests


class WechatWork:
    def __init__(self, url: str):
        self.url = url
        pass

    # 获取文件md5函数
    def get_file_md5(self, filepath):
        myhash = hashlib.md5()
        f = open(filepath, "rb")
        while True:
            b = f.read(8096)
            if not b:
                break
            myhash.update(b)
        f.close
        # print(myhash.hexdigest())
        return myhash.hexdigest()

    # 获取文件的Base64编码
    def get_file_base64(self, filepath):
        if not os.path.isfile(filepath):
            return
        with open(filepath, "rb") as f:
            image = f.read()
            image_base64 = str(base64.b64encode(
                image), encoding='utf-8')  # 这里要说明编码，否则不成功
        return image_base64

    def send_image_message(self, file):
        md5 = self.get_file_md5(file.name)
        base64_data = self.get_file_base64(file.name)
        json = {
            "msgtype": "image",
            "image": {
                "base64": base64_data,
                "md5": md5
            }
        }
        return self.send(json)

    def send(self, json):
        try:
            headers = {"Content-Type": "application/json"}  # http数据头，类型为json
            r = requests.post(self.url, headers=headers, json=json)
            return r.json()
        except:
            print_exc()