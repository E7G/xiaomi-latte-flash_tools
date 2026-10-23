"""Run the production Bash decision helper, not a Python reimplementation.

No sysfs access, synthetic temperatures only. Escalation is immediate while
cooling thresholds, rate limits and the existing sampling period stay unchanged.
"""
import random
import re
import subprocess
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'device_files/mipad2-thermal-guard'


def policy_source():
    text=SOURCE.read_text()
    start=text.index('next_state() {')
    end=text.index('\n}\n',start)+3
    return text[start:end]


def decisions(rows):
    script='set -u\n'+policy_source()+\
      '\nwhile IFS=" " read -r state temp; do\n'+\
      ' if out=$(next_state "$state" "$temp"); then printf "%s\\n" "$out"; else printf "ERROR\\n"; fi\n'+\
      'done\n'
    p=subprocess.run(['bash','-c',script],input=''.join(f'{s} {t}\n' for s,t in rows),capture_output=True,text=True,timeout=30)
    if p.returncode or p.stderr:
        raise RuntimeError(p.stderr)
    return [None if x=='ERROR' else int(x) for x in p.stdout.splitlines()]


def oracle(state,temp):
    required=3 if temp>=80000 else 2 if temp>=74000 else 1 if temp>=67000 else 0
    if required>state:
        return required
    if state>0 and temp<=[0,61000,68000,74000][state]:
        return state-1
    return state


class ThermalGuardTests(unittest.TestCase):
    def test_shell_syntax(self):
        subprocess.run(['bash','-n',str(SOURCE)],check=True)

    def test_jump_to_hottest_in_one_poll(self):
        self.assertEqual(decisions([(0,81000),(1,81000),(2,81000),(3,81000)]),[3,3,3,3])

    def test_jump_to_hot_in_one_poll(self):
        self.assertEqual(decisions([(0,75000),(1,75000)]),[2,2])

    def test_exact_boundary_and_hysteresis(self):
        temperatures=sorted({1,119999,*[k+d for k in (61000,67000,68000,74000,80000) for d in (-1,0,1)]})
        rows=[(state,temp) for state in range(4) for temp in temperatures]
        self.assertEqual(decisions(rows),[oracle(s,t) for s,t in rows])

    def test_randomized_production_decisions(self):
        rng=random.Random(72016)
        rows=[(rng.randrange(4),rng.randrange(1,120000)) for _ in range(512)]
        self.assertEqual(decisions(rows),[oracle(s,t) for s,t in rows])

    def test_cooling_remains_conservative_one_step(self):
        self.assertEqual(decisions([(3,50000),(2,50000),(1,50000),(0,50000)]),[2,1,0,0])

    def test_hold_current_level_in_hysteresis_band(self):
        self.assertEqual(decisions([(1,62000),(2,69000),(3,75000)]),[1,2,3])

    def test_invalid_read_does_not_invent_new_state(self):
        self.assertEqual(decisions([(0,'NaN'),(0,0),(0,-1),(0,120000),('x',75000),(4,75000)]),[None]*6)

    def test_main_only_commits_successful_state(self):
        text=SOURCE.read_text()
        self.assertIn('new_state=$(next_state "$state" "$t") || { sleep 3; continue; }\n    state=$new_state',text)
        self.assertNotIn('state=$(next_state',text.replace('new_state=$(next_state',''))

    def test_existing_ceiling_values_and_period_unchanged(self):
        text=SOURCE.read_text()
        self.assertEqual(re.findall(r'[0-3]\) maxfreq=(\d+);',text),['2240000','1840000','1600000','1330000'])
        self.assertIn('sleep 3\ndone',text)


if __name__=='__main__':
    unittest.main()
