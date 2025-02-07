#!/usr/bin/env python3
from configparser import ConfigParser
import uuid
import struct
import sys
from os import path, mkdir

type_2_guid = {
    # official guid for gpt partition type
    'fat': 'ebd0a0a2-b9e5-4433-87c0-68b6b72699c7',
    'esp': 'c12a7328-f81f-11d2-ba4b-00a0c93ec93b',
    'linux': '0fc63daf-8483-4772-8e79-3d69d8477de4',
    'linux-swap': '0657fd6d-a4ab-43c4-84e5-0933c84b4f4f',
    # generated guid for android
    'boot': '49a4d17f-93a3-45c1-a0de-f50b2ebe2599',
    'recovery': '4177c722-9e92-4aab-8644-43502bfd5506',
    'misc': 'ef32a33b-a409-486c-9141-9ffb711f6266',
    'metadata': '20ac26be-20b7-11e3-84c5-6cfdb94711e9',
    'tertiary': '767941d0-2085-11e3-ad3b-6cfdb94711e9',
    'factory': '9fdaa6ef-4b3f-40d2-ba8d-bff16bfb887b',
}

def zero_pad(s: bytes, size: int):
    if len(s) > size:
        print('error', len(s))
    s += bytes(size - len(s))
    return s

def preparse_partitions(gpt_in, cfg):
    with open(gpt_in, 'r') as f:
        data = f.read()
    partitions = cfg.get('base', 'partitions').split()
    for l in data.split('\n'):
        words = l.split()
        if len(words) > 2:
            if words[0] == 'partitions' and words[1] == '+=':
                partitions += words[2:]
    return partitions

def main():
    if len(sys.argv) == 2 and sys.argv[1] == 'help':
        print('Usage : ', sys.argv[0], 'gpt.ini')
        print(' write binary to stdout')
        sys.exit(1)

    # 读取配置文件
    gpt_in = "gpt.ini" if len(sys.argv) < 2 else sys.argv[1]
    cfg = ConfigParser()
    cfg.read(gpt_in)
    part = preparse_partitions(gpt_in, cfg)

    magic = 0x6A8B0DA1
    start_lba = 0
    if cfg.has_option('base', 'start_lba'):
        start_lba = cfg.getint('base', 'start_lba')

    # 有效的分区数量
    npart = len(part)
    # 输出分区信息
    if not path.exists('images/'):
        mkdir("images/")
    with open("images/gpt.bin", 'wb') as out:
        out.write(struct.pack('<I', magic))
        out.write(struct.pack('<I', start_lba))
        out.write(struct.pack('<I', npart))
        for p in part:
            # 分区长度
            length = cfg.get('partition.' + p, 'len')
            out.write(struct.pack('<i', int(length)))
            # 分区标签
            label = cfg.get('partition.' + p, 'label').encode('utf-16le')
            out.write(zero_pad(label, 36 * 2))
            # 分区类型
            guid_type = cfg.get('partition.' + p, 'type')
            guid_type = uuid.UUID(type_2_guid[guid_type])
            out.write(guid_type.bytes_le)
            # 分区guid
            if cfg.has_option("partition." + p, "guid"):
                guid = uuid.UUID(cfg.get('partition.' + p, 'guid'))
            else:
                guid = uuid.uuid4()
            out.write(guid.bytes_le)

if __name__ == "__main__":
    main()