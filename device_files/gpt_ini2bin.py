#!/usr/bin/env python3
import struct
import sys
import uuid
from argparse import ArgumentParser
from configparser import ConfigParser
from pathlib import Path

type_2_guid = {
    # official guid for gpt partition type
    'fat': 'EBD0A0A2-B9E5-4433-87C0-68B6B72699C7',
    'esp': 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B',
    'linux': '0FC63DAF-8483-4772-8E79-3D69D8477DE4',
    'linux-swap': '0657FD6D-A4AB-43C4-84E5-0933C84B4F4F',
    # generated guid for android
    'bootloader': '2568845D-2332-4675-BC39-8FA5A4748D15',
    'boot': '49A4D17F-93A3-45C1-A0DE-F50B2EBE2599',
    'recovery': '4177C722-9E92-4AAB-8644-43502BFD5506',
    'misc': 'EF32A33B-A409-486C-9141-9FFB711F6266',
    'metadata': '20AC26BE-20B7-11E3-84C5-6CFDB94711E9',
    'tertiary': '767941D0-2085-11E3-AD3B-6CFDB94711E9', # Fastboot
    'factory': '8F68CC74-C5E5-48DA-BE91-A0C8C15E9C80',
    'factory(alt)': '9FDAA6EF-4B3F-40D2-BA8D-BFF16BFB887B',
    'system': '38F428E6-D326-425D-9140-6E0EA133647C',
    'data': 'DC76DDA9-5AC1-491C-AF42-A82591580C0D',
}

parser = ArgumentParser()
parser.add_argument('-c','--config', default='gpt.ini')
parser.add_argument('output', nargs='?', default='gpt.bin', help='output file')
args = parser.parse_args()

def zero_pad(s: bytes, size: int):
    if len(s) > size:
        print('error', len(s))
    s += bytes(size - len(s))
    return s

def preparse_partitions(gpt_in, cfg):
    with open(gpt_in) as f:
        data = f.read()
    partitions = cfg.get('base', 'partitions').split()
    for line in data.split('\n'):
        words = line.split()
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
    cfg = ConfigParser()
    cfg.read(args.config)
    part = preparse_partitions(args.config, cfg)

    magic = 0x6A8B0DA1
    start_lba = 0
    if cfg.has_option('base', 'start_lba'):
        start_lba = cfg.getint('base', 'start_lba')

    # 有效的分区数量
    npart = len(part)
    output_file = Path(args.output)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    # 输出分区信息
    with open(output_file, 'wb') as out:
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