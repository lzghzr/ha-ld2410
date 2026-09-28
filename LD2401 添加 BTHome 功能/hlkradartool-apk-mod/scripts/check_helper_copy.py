# -*- coding: utf-8 -*-
"""Keep the skill's copy of the pipeline in step with the project.

    python -B scripts/check_helper_copy.py            # compare (exit 1 on drift)
    python -B scripts/check_helper_copy.py --update   # copy project -> skill
    python -B scripts/check_helper_copy.py --project D:\\LD24

Why this exists: the pipeline sources (the helper classes, the patch scripts and the delivery check)
are hand-written and cannot be re-downloaded, so the skill carries a copy in case the project
directory is cleaned up.  The project copy stays the one the build runs, so this script reports
every difference by hash - run it after touching either side.

Deliberately NOT carried here:
  * the signing key pair - it is a private key, it stays in the project only (this script just
    reports whether it is still there and prints the certificate fingerprint);
  * apk/tree (decoded tree) and apk/tools (apktool / d8 / apksigner / zipalign / android.jar /
    jadx / cfr) - regenerable or downloadable, see SKILL.md 一;
  * the stock base package - downloadable, see SKILL.md 一.
"""
import argparse
import hashlib
import shutil
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent
DEFAULT_PROJECT = Path(r'C:\AgentWorkspace\LD24')

# project-relative source  ->  skill-relative destination
FILES = [
    ('apk/helper/CustomFwHelper.java', 'helper/CustomFwHelper.java'),
    ('apk/helper/OutControlHelper.java', 'helper/OutControlHelper.java'),
    ('apk/helper/build_all.py', 'helper/build_all.py'),
    ('apk/helper/minimal_fix.py', 'helper/minimal_fix.py'),
    ('apk/helper/patch_smali.py', 'helper/patch_smali.py'),
    ('apk/helper/patch_a601_popup.py', 'helper/patch_a601_popup.py'),
    ('apk/helper/patch_bthome_key.py', 'helper/patch_bthome_key.py'),
    ('apk/helper/patch_onframe_hook.py', 'helper/patch_onframe_hook.py'),
    ('analysis/apk_randomkey_reset/verify_delivery.py', 'verify_delivery.py'),
]

# reported, never copied
KEYS = ['apk/keys/hlk_key.p8', 'apk/keys/hlk_cert.der']


def digest(path, n=16):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:n]


def report_keys(project):
    print('\n--- signing key pair (stays in the project, never carried here) ---')
    for rel in KEYS:
        p = project / rel
        if not p.exists():
            print('%-28s MISSING  <- 手机上就只能卸载重装了，先找回来' % rel)
        elif rel.endswith('hlk_cert.der'):
            print('%-28s present, cert sha256 %s' % (rel, digest(p, 64)))
        else:
            print('%-28s present' % rel)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', type=Path, default=DEFAULT_PROJECT)
    ap.add_argument('--update', action='store_true', help='copy the project copy over the skill copy')
    args = ap.parse_args()

    drift = 0
    for src_rel, dst_rel in FILES:
        src, dst = args.project / src_rel, SKILL / dst_rel
        if args.update:
            if not src.exists():
                print('missing in project: %s' % src_rel)
                drift += 1
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            print('updated %-32s <- %s' % (dst_rel, src_rel))
            continue
        if not src.exists():
            print('%-32s project copy missing (%s)' % (dst_rel, src_rel))
            drift += 1
        elif not dst.exists():
            print('%-32s skill copy missing' % dst_rel)
            drift += 1
        elif digest(src) != digest(dst):
            print('%-32s DIFFERS  project %s / skill %s'
                  % (dst_rel, digest(src), digest(dst)))
            drift += 1
        else:
            print('%-32s same (%s)' % (dst_rel, digest(src)))

    if args.update:
        print('\nupdated %d file(s)' % (len(FILES) - drift))
        return 0 if drift == 0 else 1
    report_keys(args.project)
    print('\n%d file(s) compared, %d need attention' % (len(FILES), drift))
    return 1 if drift else 0


if __name__ == '__main__':
    sys.exit(main())
