# -*- coding: utf-8 -*-
"""Rebuild the patched HLKRadarTool APK from scratch, one command.

    python -B apk/helper/build_all.py            # reuse apk/tree if present
    python -B apk/helper/build_all.py --fresh    # re-decode apk/tree from the stock APK

Pipeline (everything below lives under C:\\AgentWorkspace\\LD24\\apk):
  1. apktool d  doc/HLKRadarTool_release_1.6.112.apk  ->  tree/          (with --fresh)
  2. javac + d8 + baksmali the two helper classes -> helper/out_smali/    (smali for the patches)
  3. patch_smali.py    - 2026-09-25 patches: 自定义固件升级 entry, LD2401 light visibility,
                         OUT-control block (still sending FF->A6->FE at this stage)
  4. javac + d8 + baksmali the fixed OutControlHelper -> helper/out_oc_smali/,
     minimal_fix.py    - OUT block sends ONLY A6 (its FE used to close the page's session)
  5. patch_a601_popup.py - show the native 设置成功 hint for the A601 ACK
     patch_bthome_key.py - the BTHome-key row: OutControlHelper.addKeyRow in init() plus a
                         display-only OutControlHelper.onInfo hook on onReceiveInfoMessage
  6. apktool b -> dist/hlk_rebuilt.apk; swap classes2.dex into the stock APK; zipalign; apksigner
     with the SAME key (keys/hlk_key.p8 + keys/hlk_cert.der) so it installs over the phone's copy.

Every step asserts its own artifact markers; a step that silently produces nothing is a bug
(that is exactly how the 2026-09-25 build shipped stale smali once).
"""
import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

APK = Path(r'C:\AgentWorkspace\LD24\apk')
ROOT = APK.parent
TREE = APK / 'tree'
HELPER = APK / 'helper'
TOOLS = APK / 'tools'
KEYS = APK / 'keys'
DIST = APK / 'dist'
STOCK = ROOT / 'doc' / 'HLKRadarTool_release_1.6.112.apk'
DELIVERED = ROOT / 'doc' / 'HLKRadarTool_1.6.112_customfw_light.apk'

JAVA = r'C:\Program Files\Common Files\Oracle\Java\javapath\java.exe'
JAVAC = r'C:\Program Files\Common Files\Oracle\Java\javapath\javac.exe'
APKTOOL = str(TOOLS / 'apktool-cli.jar')
D8 = str(TOOLS / 'android-14' / 'lib' / 'd8.jar')
ANDROID_JAR = str(TOOLS / 'android.jar')
ZIPALIGN = TOOLS / 'android-14' / 'zipalign.exe'
APKSIGNER_JAR = TOOLS / 'android-14' / 'lib' / 'apksigner.jar'
KEY, CERT = KEYS / 'hlk_key.p8', KEYS / 'hlk_cert.der'


def run(cmd, **kw):
    print('   $', ' '.join(str(c) for c in cmd[:4]), '...' if len(cmd) > 4 else '')
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def compile_helpers(sources, work):
    out_cls, out_dex, out_smali = (HELPER / (work + s) for s in ('_cls', '_dex', '_smali'))
    for d in (out_cls, out_dex, out_smali):
        shutil.rmtree(d, ignore_errors=True)
    out_dex.mkdir(parents=True)                       # d8 needs the directory to exist
    run([JAVAC, '-source', '8', '-target', '8', '-nowarn', '-encoding', 'UTF-8', '-cp', ANDROID_JAR,
         '-d', out_cls] + [str(HELPER / s) for s in sources])
    classes = sorted(str(p) for p in out_cls.rglob('*.class'))
    assert classes, 'javac produced no classes'
    run([JAVA, '-cp', D8, 'com.android.tools.r8.D8', '--release', '--min-api', '21',
         '--output', out_dex] + classes, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert (out_dex / 'classes.dex').exists(), 'd8 produced no dex'
    run([JAVA, '-cp', APKTOOL, 'com.android.tools.smali.baksmali.Main', 'd',
         out_dex / 'classes.dex', '-o', out_smali], stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    got = sorted(p.name for p in (out_smali / 'com/hlk/hlkradartool/tool').glob('*.smali'))
    assert got, 'baksmali produced no smali'
    print('   compiled %d class(es) -> %s' % (len(classes), ', '.join(got)))
    return out_smali


def patch_steps():
    for script in ('patch_smali.py', 'minimal_fix.py', 'patch_a601_popup.py',
               'patch_bthome_key.py', 'patch_onframe_hook.py'):
        print('   running', script)
        subprocess.run([sys.executable, '-B', str(HELPER / script)], check=True)


def is_signature(name):
    """Only the JAR-signature entries are dropped; META-INF/services and *.version files ship
    with the stock APK (dropping those was an unnecessary difference from the release build)."""
    if not name.startswith('META-INF/'):
        return False
    base = name[len('META-INF/'):]
    if '/' in base:
        return False
    up = base.upper()
    return up == 'MANIFEST.MF' or up.endswith(('.SF', '.RSA', '.DSA', '.EC'))


def build_apk():
    DIST.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(TREE / 'build', ignore_errors=True)
    rebuilt = DIST / 'hlk_rebuilt.apk'
    if rebuilt.exists():
        rebuilt.unlink()
    run([JAVA, '-jar', APKTOOL, 'b', TREE, '-o', rebuilt])

    new_dex = zipfile.ZipFile(rebuilt).read('classes2.dex')
    for marker in (b'CustomFwHelper', b'OutControlHelper', b'addKeyRow', b'onInfo',
                   b'requestReset', b'onResetClick', b'armReset',
                   b'disarmReset', b'styleResetAction', b'hexOf', b'onFrame', b'LAST_KEY',
                   b'A600', b'A601', b'BTHome'):
        assert marker in new_dex, 'rebuilt dex missing ' + repr(marker)
    for bad in (b'SessionHelper', b'addPickButton', b'BtKeyHelper'):
        assert bad not in new_dex, 'rebuilt dex still contains ' + repr(bad)

    mod = DIST / 'hlk_mod.apk'
    stock = zipfile.ZipFile(STOCK)
    out = zipfile.ZipFile(mod, 'w')
    for info in stock.infolist():
        if info.filename == 'classes2.dex' or is_signature(info.filename):
            continue
        ni = zipfile.ZipInfo(info.filename, date_time=info.date_time)
        ni.compress_type = info.compress_type
        ni.external_attr = info.external_attr
        out.writestr(ni, stock.read(info.filename))
    ni = zipfile.ZipInfo('classes2.dex', (2026, 9, 27, 12, 0, 0))
    ni.compress_type = zipfile.ZIP_DEFLATED
    out.writestr(ni, new_dex)
    out.close()
    assert zipfile.ZipFile(mod).read('classes2.dex') == new_dex

    aligned = DIST / 'hlk_mod_aligned.apk'
    signed = DIST / 'HLKRadarTool_1.6.112_customfw_light_signed.apk'
    run([ZIPALIGN, '-f', '-p', '4', mod, aligned])
    run([JAVA, '-cp', APKSIGNER_JAR, 'com.android.apksigner.ApkSignerTool', 'sign',
         '--key', KEY, '--cert', CERT, '--out', signed, aligned])
    return signed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fresh', action='store_true', help='re-decode the apktool tree first')
    ap.add_argument('--no-deliver', action='store_true', help='do not overwrite doc/…customfw_light.apk')
    ap.add_argument('--skip-patches', action='store_true', help='tree is already patched')
    args = ap.parse_args()

    for p in (APKTOOL, D8, ANDROID_JAR, ZIPALIGN, APKSIGNER_JAR, KEY, CERT, STOCK):
        assert Path(p).exists(), 'missing ' + str(p)

    if args.fresh:
        print('1. apktool d -> tree/')
        shutil.rmtree(TREE, ignore_errors=True)
        run([JAVA, '-jar', APKTOOL, 'd', STOCK, '-o', TREE])
    assert TREE.exists(), 'no tree: run with --fresh'

    print('2. compile CustomFwHelper + OutControlHelper')
    compile_helpers(('CustomFwHelper.java', 'OutControlHelper.java'), 'out')

    print('3-5. apply the smali patches')
    if args.skip_patches:
        print('   (skipped: tree already patched)')
    compile_helpers(('OutControlHelper.java',), 'out_oc')   # minimal_fix.py and
                                                            # patch_bthome_key.py read this
    if not args.skip_patches:
        patch_steps()

    print('6. rebuild, swap into the stock APK, align, sign')
    signed = build_apk()

    print('   signed:', signed)
    import hashlib
    digest = hashlib.sha256(signed.read_bytes()).hexdigest()
    print('   sha256:', digest)

    if not args.no_deliver:
        shutil.copyfile(signed, DELIVERED)
        print('   delivered to', DELIVERED)
    print('OK - install with: adb install -r "%s"' % signed)


if __name__ == '__main__':
    main()
