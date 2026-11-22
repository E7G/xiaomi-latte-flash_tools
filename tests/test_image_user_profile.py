from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "build_rootfs.sh").read_text()
START = SCRIPT.index("config_zsh_profile() {")
END = SCRIPT.index("\nconfig_user() {", START)
PROFILE = SCRIPT[START:END]

FIXTURE = r"""
umask 077
UserName=tablet
run() {
    command=$1
    shift
    if [[ "$command" == install ]]; then
        test "$1 $2 $3" = "-m 0600 -o"
        owner=$4
        test "$5 $6" = "-g $owner"
        case "$8" in
            /home/tablet/.zshrc) test "$owner" = tablet ;;
            /root/.zshrc) test "$owner" = root ;;
            *) exit 22 ;;
        esac
        /usr/bin/install -m 0600 "$PWD$7" "$PWD$8"
        return
    fi
    args=("$@")
    i=$(($# - 1))
    path=$(printf '%s\n' "$@" | tail -n 1)
    test "$path" = /home/tablet/.zshrc
    args[$i]="$PWD$path"
    case "$command" in
        sed|grep) "/usr/bin/$command" "${args[@]}" ;;
        zsh) test "$1" = -n && test -r "${args[$i]}" ;;
        *) exit 23 ;;
    esac
}
"""


class ImageProfileTests(unittest.TestCase):
    def invoke(self, template):
        td = tempfile.TemporaryDirectory(prefix="mipad2-profile-")
        self.addCleanup(td.cleanup)
        p = Path(td.name)
        package = p / "usr/share/oh-my-zsh/zshrc"
        package.parent.mkdir(parents=True)
        (p / "home/tablet").mkdir(parents=True)
        (p / "root").mkdir()
        package.write_text(template)
        package.chmod(0o644)
        result = subprocess.run(["bash", "-e", "-c", FIXTURE + PROFILE + "\nconfig_zsh_profile\n"],
                                cwd=p, text=True, capture_output=True)
        self.assertEqual(package.read_text(), template)
        self.assertEqual(stat.S_IMODE(package.stat().st_mode), 0o644)
        return p, result

    def test_restrictive_umask_and_package_template_unchanged(self):
        template = '# ZSH_CUSTOM=/default\nZSH_THEME="robbyrussell"\nplugins=(git)\n'
        p, result = self.invoke(template)
        self.assertEqual(result.returncode, 0, result.stderr)
        user, root = p / "home/tablet/.zshrc", p / "root/.zshrc"
        self.assertEqual(stat.S_IMODE(user.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o600)
        self.assertEqual(user.read_bytes(), root.read_bytes())
        self.assertEqual(user.read_text().splitlines(), [
            "ZSH_CUSTOM=/usr/share/zsh", 'ZSH_THEME="ys"',
            "plugins=(git sudo safe-paste extract command-not-found zsh-autosuggestions zsh-syntax-highlighting)",
        ])

    def test_missing_template_slot_aborts(self):
        p, result = self.invoke('# ZSH_CUSTOM=/default\nplugins=(git)\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((p / "root/.zshrc").exists())


if __name__ == "__main__":
    unittest.main()
