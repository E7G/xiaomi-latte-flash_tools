#!/usr/bin/python3
"""Launch the source candidate with private settings, never a diagnostic profile."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


PROFILE = {
    'MIPAD2_CAPTURE_CURRENT_CAPS': '1',
    'MIPAD2_CAPTURE_RAW_DIRECT': '1',
    'MIPAD2_CAPTURE_RAW_ASYNC': '0',
    'MIPAD2_CAPTURE_COPY': '1',
    'MIPAD2_CAPTURE_ALLOCATION_GUARD': '1',
    'MIPAD2_CAPTURE_DECOUPLE': '0',
    'MIPAD2_CAPTURE_DECOUPLE_SMALL': '0',
    'MIPAD2_ANDROID_VIDEO_PROFILE': '1',
    'MIPAD2_RECORDING_QUALITY': '1',
    'MIPAD2_VA_ASYNC_DEPTH': '2',
    'MIPAD2_H264_LOW_LATENCY': '1',
    'MIPAD2_PREVIEW_QOS_OFF': '1',
    'MIPAD2_PREVIEW_GPU_ROTATION': '1',
    'MIPAD2_MP4_ROTATION_MATRIX': '1',
}


def environment(inherited, config, config_home, cache_home):
    env = {k: v for k, v in inherited.items()
           if not k.startswith(('MIPAD2_', 'GST_')) and k not in {
               'LD_PRELOAD', 'LD_LIBRARY_PATH', 'GSK_DEBUG', 'GSK_RENDERER',
               'RUST_LOG', 'GSETTINGS_SCHEMA_DIR', 'GSETTINGS_BACKEND'}}
    env.update(PROFILE)
    env.update(GSETTINGS_BACKEND='keyfile', XDG_CONFIG_HOME=str(config_home),
               XDG_CACHE_HOME=str(cache_home),
               GSETTINGS_SCHEMA_DIR=config['prefix']+'/share/glib-2.0/schemas',
               GST_PLUGIN_PATH=':'.join(config['plugin_directories']),
               GST_PLUGIN_PATH_1_0=':'.join(config['plugin_directories']),
               GST_PLUGIN_SYSTEM_PATH='/usr/lib/gstreamer-1.0',
               GST_PLUGIN_SYSTEM_PATH_1_0='/usr/lib/gstreamer-1.0',
               GST_REGISTRY=str(cache_home/'registry.bin'),
               GST_REGISTRY_1_0=str(cache_home/'registry.bin'),
               LIBVA_DRIVER_NAME='i965', GST_VA_ALL_DRIVERS='1')
    return env


def main():
    config = json.loads(Path(__file__).with_name('candidate-profile.json').read_text())
    home = Path.home()
    config_home = home/'.config'/config['profile_name']
    cache_home = home/'.cache'/config['profile_name']
    # Snapshot retains its upstream application ID/portal identity. Do not
    # silently activate an already-running stable binary through that bus name.
    owner = subprocess.run([
        'gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus',
        '--object-path', '/org/freedesktop/DBus', '--method',
        'org.freedesktop.DBus.NameHasOwner', 'org.gnome.Snapshot'],
        capture_output=True, text=True, timeout=10)
    if owner.returncode or owner.stdout.strip() != '(false,)':
        raise SystemExit('Close the existing Snapshot window before launching the source candidate.')
    config_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    cache_home.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Preserve the real photo/video directories, but never execute shell config.
    normal_config = Path(os.environ.get('XDG_CONFIG_HOME', home/'.config'))
    for name in ('user-dirs.dirs', 'user-dirs.locale'):
        source = normal_config/name
        if source.is_file():
            shutil.copyfile(source, config_home/name)
    env = environment(os.environ, config, config_home, cache_home)
    executable = config['prefix']+'/bin/snapshot'
    os.execve(executable, [executable, *sys.argv[1:]], env)


if __name__ == '__main__':
    main()
