"""The 7.2 producer must restore and actually stage the LPAT31 module roles."""
from pathlib import Path
import subprocess
import tempfile
import unittest

TEXT = (Path(__file__).resolve().parents[1] / "scripts/build_kernel_package.sh").read_text()
HELP = TEXT.split("# BEGIN MIPAD2_72_RELEASE_MODULES\n", 1)[1].split(
    "# END MIPAD2_72_RELEASE_MODULES", 1)[0]
OPTIONS = (
    "CONFIG_IIO_CHT_WC_ADC=m", "CONFIG_INTEL_CHTWC_THERMAL=m",
    "CONFIG_NFT_NAT=m", "CONFIG_NFT_MASQ=m", "CONFIG_EROFS_FS=m",
)
MODULES = (
    "drivers/iio/adc/intel-chtwc-adc", "drivers/acpi/pmic/intel_pmic_chtwc_thermal",
    "fs/erofs/erofs", "net/netfilter/nft_nat", "net/netfilter/nft_masq", "net/netfilter/nft_chain_nat",
)


class ReleaseModules(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="mipad2 module stage ")
        self.addCleanup(d.cleanup)
        self.stage = Path(d.name)
        self.config = self.stage / "config"
        self.config.write_text("\n".join(OPTIONS) + "\n")

    def path(self, name):
        return self.stage / "kernel" / (name + ".ko.zst")

    def call(self, family="7.2"):
        return subprocess.run(
            ["bash", "-c", "set -Eeuo pipefail\nkernel_family=$1\n" + HELP
             + '\nrequire_72_release_config "$2"\nrequire_72_release_modules "$3"',
             "fixture", family, str(self.config), str(self.stage)],
            capture_output=True, text=True, timeout=5,
        )

    def populate(self):
        for name in MODULES:
            p = self.path(name)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"staged fixture module")

    def test_legacy_family_untouched(self):
        self.config.unlink()
        self.assertEqual(self.call("6.14").returncode, 0)

    def test_correctly_built_stage_is_accepted(self):
        self.populate()
        self.assertEqual(self.call().returncode, 0)

    def test_each_required_config_value_is_exact(self):
        self.populate()
        for option in OPTIONS:
            with self.subTest(option=option):
                self.config.write_text("\n".join(o if o != option else o[:-1] + "y" for o in OPTIONS) + "\n")
                result = self.call()
                self.assertNotEqual(result.returncode, 0, result)
                self.assertIn(option, result.stderr)

    def test_each_compiled_module_is_required(self):
        self.populate()
        for name in MODULES:
            with self.subTest(module=name):
                p = self.path(name)
                p.unlink()
                result = self.call()
                self.assertNotEqual(result.returncode, 0, result)
                self.assertIn(name + ".ko.zst", result.stderr)
                p.write_bytes(b"restored fixture")

    def test_empty_and_symlink_modules_do_not_pass(self):
        self.populate()
        p = self.path(MODULES[0])
        p.write_bytes(b"")
        self.assertNotEqual(self.call().returncode, 0)
        p.unlink()
        p.symlink_to(self.path(MODULES[1]))
        self.assertNotEqual(self.call().returncode, 0)

    def test_config_check_precedes_compile_and_module_check_precedes_packaging(self):
        config = TEXT.index("\nrequire_72_release_config .config\n")
        compile_at = TEXT.index('\nmake -j')
        install = TEXT.index("DEPMOD=true modules_install")
        modules = TEXT.index('\nrequire_72_release_modules "$mod_dir"\n')
        package = TEXT.index("\nbsdtar --zstd -cf")
        self.assertTrue(config < compile_at < install < modules < package)


if __name__ == "__main__":
    unittest.main(verbosity=2)
