# Installation
1. Install python-wechatPc
```
pip3 install -U git+https://github.com/tedrolin/python-wechatPc
```

2. Install EFB related stuff
```commandline
pip3 install efb-telegram-master
```

3. Install me
```
pip3 install -U git+https://github.com/tedrolin/efb-wechat-pc-slave
```

4. Configure
```
mkdir -p ~/.ehforwarderbot/profiles/default/tedrolin.wechat_pc
touch ~/.ehforwarderbot/profiles/default/tedrolin.wechat_pc/config.yaml
```

5. Feed the config.yaml with following content
```yaml
uri: "ws://127.0.0.1:5678"  # ws path to wechat pc 
```

6. Add me to `~/.ehforwarderbot/profiles/default/`
```
slave_channels:
- tedrolin.wechatPc
```

7. Run `ehforwarderbot`