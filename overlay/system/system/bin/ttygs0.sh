#!/system/bin/sh
DEV=/dev/ttyGS0

# 等待设备
while [ ! -c "$DEV" ]; do sleep 0.1; done

chcon u:object_r:tty_device:s0 "$DEV"

# 设置 tty 为 sane 模式
stty sane -F "$DEV" 2>/dev/null

# 启动 shell 并绑定
exec /system/bin/sh <"$DEV" >"$DEV" 2>&1
