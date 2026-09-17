#!/usr/bin/python3
import fcntl
import glob
import os
import struct
import time

TARGET_NAME = "hid-over-i2c 2808:509C Keyboard"
EV_SYN = 0
EV_KEY = 1
SYN_REPORT = 0
KEY_A = 30
KEY_LEFT = 105
KEY_HOME = 102
KEY_MENU = 139
KEY_BACK = 158
KEY_LEFTALT = 56
KEY_LEFTMETA = 125
BUS_VIRTUAL = 0x06

_IOC_NRBITS = 8
_IOC_TYPEBITS = 8
_IOC_SIZEBITS = 14
_IOC_NRSHIFT = 0
_IOC_TYPESHIFT = _IOC_NRSHIFT + _IOC_NRBITS
_IOC_SIZESHIFT = _IOC_TYPESHIFT + _IOC_TYPEBITS
_IOC_DIRSHIFT = _IOC_SIZESHIFT + _IOC_SIZEBITS
_IOC_NONE = 0
_IOC_WRITE = 1

def _IOC(direction, typ, nr, size):
    return ((direction << _IOC_DIRSHIFT) |
            (ord(typ) << _IOC_TYPESHIFT) |
            (nr << _IOC_NRSHIFT) |
            (size << _IOC_SIZESHIFT))

def _IO(typ, nr):
    return _IOC(_IOC_NONE, typ, nr, 0)

def _IOW(typ, nr, size):
    return _IOC(_IOC_WRITE, typ, nr, size)

UI_SET_EVBIT = _IOW('U', 100, 4)
UI_SET_KEYBIT = _IOW('U', 101, 4)
UI_DEV_CREATE = _IO('U', 1)
UI_DEV_DESTROY = _IO('U', 2)
EVIOCGRAB = _IOW('E', 0x90, 4)
INPUT_EVENT = struct.Struct('@llHHi')


def find_device():
    while True:
        for name_path in glob.glob('/sys/class/input/event*/device/name'):
            try:
                if open(name_path, encoding='utf-8').read().strip() == TARGET_NAME:
                    event = name_path.split('/')[-3]
                    return '/dev/input/' + event
            except OSError:
                pass
        time.sleep(1)


def emit(fd, code, value):
    os.write(fd, INPUT_EVENT.pack(0, 0, EV_KEY, code, value))


def sync(fd):
    os.write(fd, INPUT_EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))


def setup_uinput():
    fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
    fcntl.ioctl(fd, UI_SET_EVBIT, EV_KEY)
    for key in (KEY_A, KEY_LEFT, KEY_LEFTALT, KEY_LEFTMETA):
        fcntl.ioctl(fd, UI_SET_KEYBIT, key)
    name = b'Mi Pad 2 navigation keys'
    data = struct.pack('80sHHHHI' + 'i' * 256,
                       name, BUS_VIRTUAL, 0x2808, 0x509c, 1, 0,
                       *([0] * 256))
    os.write(fd, data)
    fcntl.ioctl(fd, UI_DEV_CREATE)
    time.sleep(0.25)
    return fd


def run():
    path = find_device()
    infd = os.open(path, os.O_RDONLY)
    fcntl.ioctl(infd, EVIOCGRAB, 1)
    outfd = setup_uinput()
    print(f'grabbing {path}: {TARGET_NAME}', flush=True)
    try:
        buf = b''
        while True:
            chunk = os.read(infd, INPUT_EVENT.size * 16)
            if not chunk:
                raise OSError('input device disappeared')
            buf += chunk
            while len(buf) >= INPUT_EVENT.size:
                raw, buf = buf[:INPUT_EVENT.size], buf[INPUT_EVENT.size:]
                _, _, etype, code, value = INPUT_EVENT.unpack(raw)
                if etype != EV_KEY or value == 2:
                    continue
                if code == KEY_HOME:
                    emit(outfd, KEY_LEFTMETA, value)
                    sync(outfd)
                    print(f'HOME {value}', flush=True)
                elif code == KEY_MENU:
                    if value:
                        emit(outfd, KEY_LEFTMETA, 1)
                        emit(outfd, KEY_A, 1)
                    else:
                        emit(outfd, KEY_A, 0)
                        emit(outfd, KEY_LEFTMETA, 0)
                    sync(outfd)
                    print(f'MENU {value}', flush=True)
                elif code == KEY_BACK:
                    if value:
                        emit(outfd, KEY_LEFTALT, 1)
                        emit(outfd, KEY_LEFT, 1)
                    else:
                        emit(outfd, KEY_LEFT, 0)
                        emit(outfd, KEY_LEFTALT, 0)
                    sync(outfd)
                    print(f'BACK {value}', flush=True)
    finally:
        try:
            fcntl.ioctl(infd, EVIOCGRAB, 0)
        except OSError:
            pass
        try:
            fcntl.ioctl(outfd, UI_DEV_DESTROY)
        except OSError:
            pass
        os.close(infd)
        os.close(outfd)


if __name__ == '__main__':
    while True:
        try:
            run()
        except Exception as exc:
            print(f'navkeys error: {exc}', flush=True)
            time.sleep(1)
