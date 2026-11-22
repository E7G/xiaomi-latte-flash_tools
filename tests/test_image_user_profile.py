from pathlib import Path
import stat
import subprocess
import tempfile
import unittest


SCRIPT = (Path(__file__).resolve().parents[1] / "build_rootfs.sh").read_text()
START = SCRIPT.index("config_zsh_profile() {")
END = SCRIPT.index("\nconfig_user() {", START)
PROFILE = SCRIPT[START:END]
PKGFILE = SCRIPT[SCRIPT.index("update_pkgfile() {"):SCRIPT.index("\nall() {")]

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


class OptionalPackageIndexTests(unittest.TestCase):
    def invoke(self, statuses):
        fixture = """
n=0
run() {
    test "$*" = 'timeout --kill-after=5s 60s pkgfile --update'
    n=$((n+1))
    echo "attempt $n"
    return "${statuses[$((n-1))]}"
}
sleep() {
    test "$1" = 5
    echo 'retry wait'
}
"""
        shell = f"statuses=({' '.join(map(str, statuses))})\n" + fixture + PKGFILE + "\nupdate_pkgfile\n"
        return subprocess.run(["bash", "-e", "-c", shell], text=True, capture_output=True)

    def test_success_and_short_retry(self):
        good = self.invoke([0])
        self.assertEqual(good.returncode, 0)
        self.assertEqual(good.stdout.splitlines(), ["attempt 1"])
        self.assertEqual(good.stderr, "")
        recovered = self.invoke([7, 0])
        self.assertEqual(recovered.returncode, 0)
        self.assertEqual(recovered.stdout.splitlines(), ["attempt 1", "retry wait", "attempt 2"])
        self.assertNotIn("Continuing without", recovered.stderr)

    def test_timeout_is_nonfatal_without_restart(self):
        for status in (124, 125, 127, 137):
            with self.subTest(status=status):
                stopped = self.invoke([status])
                self.assertEqual(stopped.returncode, 0)
                self.assertEqual(stopped.stdout.splitlines(), ["attempt 1"])
                self.assertIn(f"status {status}", stopped.stderr)
                self.assertIn("Continuing without", stopped.stderr)

    def test_at_most_three_short_failures(self):
        exhausted = self.invoke([7, 7, 7])
        self.assertEqual(exhausted.returncode, 0)
        self.assertEqual(exhausted.stdout.count("attempt "), 3)
        self.assertEqual(exhausted.stdout.count("retry wait"), 2)
        self.assertIn("Continuing without", exhausted.stderr)


if __name__ == "__main__":
    unittest.main()
