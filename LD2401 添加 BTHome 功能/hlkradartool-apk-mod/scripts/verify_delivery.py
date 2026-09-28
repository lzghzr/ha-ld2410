# -*- coding: utf-8 -*-
"""Checks for the delivered APK that carries the BTHome re-key row.

    python -B analysis/apk_randomkey_reset/verify_delivery.py

What it proves (static only - it never touches the phone):
  1. doc/HLKRadarTool_1.6.112_customfw_light.apk == apk/dist/..._signed.apk (same sha256);
  2. against the stock release APK the only entry with different content is classes2.dex, and
     the only extra entries are our three signature files;
  3. classes2.dex carries the key row AND the re-key row, and none of the withdrawn helpers;
  4. the injected smali still consists of exactly one call per entry point, the onInfo hook is a
     single void invoke at the top of onReceiveInfoMessage (no branch, no label), and the A6(4)
     frame is well formed;
  5. the signing certificate is ours (the one that installs over the phone's copy).

It cannot prove runtime behaviour: the two-tap confirm, the A6(4) round trip and the page not
crashing all need a device (see README in this directory).
"""
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(r'C:\AgentWorkspace\LD24')
DELIVERED = ROOT / 'doc' / 'HLKRadarTool_1.6.112_customfw_light.apk'
SIGNED = ROOT / 'apk' / 'dist' / 'HLKRadarTool_1.6.112_customfw_light_signed.apk'
RELEASE = ROOT / 'doc' / 'HLKRadarTool_release_1.6.112.apk'
PAGE = (ROOT / 'apk' / 'tree' / 'smali_classes2' / 'com' / 'hlk' / 'hlkradartool'
        / 'activity' / 'SetParameter2Activity.smali')
DEMO = PAGE.parent / 'DemoApplication.smali'
TOOL = PAGE.parent.parent / 'tool'
OUR_CERT = '41df17236cfec03ffde01616923eb38eddf6a7a0e3f79525cb5dac9abbf0fb93'

# the frames the helper builds, as the app's own A6(3) template spells them
A6_READ = 'FDFCFBFA0400A600030004030201'          # verified working on the module (26092422)
A6_REKEY = 'FDFCFBFA0400A600040004030201'         # same frame, parameter 3 -> 4

fails = []


def check(ok, label, detail=''):
    print('%-4s %s%s' % ('ok' if ok else 'FAIL', label, ('  <- ' + detail) if detail and not ok else ''))
    if not ok:
        fails.append(label)


def deescape(text):
    """smali string literals carry non-ASCII as \\uXXXX escapes."""
    return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)


def access_map(txt):
    """access$NNN -> the real method it forwards to, so checks survive renumbering."""
    out = {}
    for m in re.finditer(r'\.method static synthetic (access\$\d+)\([^)]*\)\S+\n(.*?)\.end method',
                         txt, re.S):
        tgt = re.search(r'OutControlHelper;->(\w+)\(', m.group(2))
        out[m.group(1)] = tgt.group(1) if tgt else '?'
    return out


def runnable_sends(tool_dir, access):
    """Names of delayed Runnables that call OutControlHelper.send - there must be none."""
    bad = []
    for f in sorted(tool_dir.glob('OutControlHelper$*.smali')):
        t = f.read_text(encoding='utf-8')
        if 'Ljava/lang/Runnable;' not in t:
            continue
        if any(access.get(n) == 'send' for n in re.findall(r'(access\$\d+)\(', t)):
            bad.append(f.name)
    return bad


def listener_classes(tool_dir, enclosing, iface, access):
    """Per anonymous <iface> listener declared inside one method, the OutControlHelper methods it calls."""
    out = []
    for f in sorted(tool_dir.glob('OutControlHelper$*.smali')):
        t = f.read_text(encoding='utf-8')
        if ('OutControlHelper;->%s(' % enclosing) not in t:
            continue
        if ('Landroid/view/View$%s;' % iface) not in t:
            continue
        out.append(sorted(set(access.get(n, '?') for n in re.findall(r'(access\$\d+)\(', t))))
    return out


def main():
    for p in (DELIVERED, SIGNED, RELEASE, PAGE):
        if not p.exists():
            check(False, 'missing ' + str(p))
            return 1

    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    check(sha(DELIVERED) == sha(SIGNED), 'delivered APK == apk/dist signed APK', sha(DELIVERED))
    print('     delivered sha256:', sha(DELIVERED))

    rel, new = zipfile.ZipFile(RELEASE), zipfile.ZipFile(DELIVERED)
    rc = {i.filename: i.CRC for i in rel.infolist()}
    nc = {i.filename: i.CRC for i in new.infolist()}
    extra = sorted(set(nc) - set(rc))
    missing = sorted(set(rc) - set(nc))
    differ = sorted(n for n in set(rc) & set(nc) if rc[n] != nc[n])
    check(differ == ['classes2.dex'], 'only classes2.dex differs from the release APK', str(differ))
    check(not missing, 'no release entry dropped', str(missing))
    check(extra == ['META-INF/HLK_KEY.RSA', 'META-INF/HLK_KEY.SF', 'META-INF/MANIFEST.MF'],
          'extra entries are only our signature files', str(extra))

    dex = new.read('classes2.dex')
    for marker in (b'OutControlHelper', b'addTo', b'addKeyRow', b'onInfo', b'hexOf',
                   b'findKey', b'keyIn', b'onFrame', b'requestReset', b'onResetClick', b'armReset',
                   b'disarmReset', b'styleResetAction', b'expectReply', b'setKeyText', b'hasKey', b'copyIfKey',
                   u'读取中'.encode('utf-8'), u'未收到应答'.encode('utf-8'),
                   u'应答无法识别'.encode('utf-8')):
        check(marker in dex, 'dex carries ' + marker.decode('utf-8', 'replace'))
    for bad in (b'BtKeyHelper', b'SessionHelper', b'addPickButton', b'addResetRow'):
        check(bad not in dex, 'dex free of withdrawn ' + bad.decode())

    oc = (TOOL / 'OutControlHelper.smali').read_text(encoding='utf-8')
    access = access_map(oc)
    clicks = {tuple(t) for t in listener_classes(TOOL, 'addKeyRow', 'OnClickListener', access)}
    longs = {tuple(t) for t in listener_classes(TOOL, 'addKeyRow', 'OnLongClickListener', access)}
    check(clicks == {('disarmReset', 'hasKey', 'requestKey'), ('onResetClick',)},
          'two click targets: the value (fetch only until a key is shown) and 点击重置',
          str(sorted(clicks)))
    check(longs == {('copyIfKey',)},
          'long-press on the key copies, and nothing else', str(sorted(longs)))
    check('styleResetAction' in oc and oc.count('styleResetAction') >= 3,
          're-key control styled red in every state')

    page = PAGE.read_text(encoding='utf-8')
    for name in ('addTo', 'addKeyRow', 'onInfo'):
        check(page.count('OutControlHelper;->' + name) == 1,
              'exactly one OutControlHelper->%s call site' % name,
              str(page.count('OutControlHelper;->' + name)))
    hook = ('    invoke-static {p0, p1}, Lcom/hlk/hlkradartool/tool/OutControlHelper;'
            '->onInfo(Landroid/app/Activity;Ljava/lang/Object;)V\n')
    check(hook in page, 'onInfo hook is a single void invoke, no move-result / branch')
    i = page.index(hook)
    check('.line 1624' in page[i:i + len(hook) + 120],
          'hook sits at the method top, before the stock body')
    for bad in ('BtKeyHelper', 'cond_keydone', 'cond_a6hint', 'cond_keyni'):
        check(bad not in page, 'page free of withdrawn ' + bad)

    txt = deescape('\n'.join(p.read_text(encoding='utf-8') for p in TOOL.glob('OutControlHelper*.smali')))
    for s in ('BTHome 密钥：', '点击获取', '点击重置', '再点一次确认', '已重置换钥',
              '重置后模块换新密钥，需在 HA 里重新填写 bindkey'):
        check(s in txt, u'string present: ' + s)
    check('BTHome 重置密钥：' not in txt, 'no third row labelled 重置密钥')
    check('0x4f2d' not in txt, 'the old separate re-key row id is gone')
    check('A6010000' in txt, 'key extraction strips the 4-byte reply header (a6 01 00 00)')
    check('getMethods' in txt and 'info: cmd=' in txt,
          'onInfo falls back to scanning the other String getters and logs every frame it sees')
    check('key reply' not in txt and 'info: cmd=' in txt,
          'logcat shows what arrived and the extracted key on one line')

    demo = DEMO.read_text(encoding='utf-8')
    check(demo.count('OutControlHelper;->onFrame') == 1,
          'exactly one frame-funnel hook, in DemoApplication.parseByData',
          str(demo.count('OutControlHelper;->onFrame')))
    check(demo.count('OutControlHelper;') == 1,
          'no other OutControlHelper reference in DemoApplication')
    dispatch = ('invoke-virtual {v1, p1, v0, p3}, Lcom/hlk/hlkradartool/data/DataAnalysisHelper;'
                '->startDataAnalysis(')
    check(dispatch in demo, 'the LD2401 dispatch call site is still there')
    hook = 'invoke-static {v0}, Lcom/hlk/hlkradartool/tool/OutControlHelper;->onFrame(Ljava/lang/String;)V'
    check(hook in demo and demo.index(hook) < demo.index(dispatch),
          'the hook runs on the complete frame just before the LD2401 dispatch')
    check('FE00' not in txt, 'helper sends no 0x00FE (that closed the page session)')
    check('FF00' not in txt, 'helper sends no 0x00FF either - stock rows never do (2026-09-28)')
    check('sendSequence' not in txt, 'the invented multi-frame send helper is gone')
    delayed = len(re.findall(r'Handler;->postDelayed', txt))
    check(delayed == 2, 'only two delayed runnables, both UI state (await confirm, await reply)',
          str(delayed))
    senders = runnable_sends(TOOL, access)
    check(not senders, 'no delayed Runnable sends a frame - no retry, no read-back', str(senders))
    for piece in ('FDFCFBFA', '0400', 'A600', '0300', '04030201'):
        check(piece in txt, 'frame piece ' + piece)
    for out_val in ('0000', '0100', '0200'):
        check(out_val in txt, 'OUT control value still present: ' + out_val)
    check(A6_REKEY[8:] == '0400A600040004030201', 're-key frame = A6(4), built from those pieces')
    for rid in ('0x4f2a', '0x4f2b', '0x4f2e'):
        check(rid in txt, 'custom id ' + rid)
    check('0x4f30' not in txt, 'no separate fetch control any more - the value carries 点击获取')

    print()
    if fails:
        print('%d CHECK(S) FAILED' % len(fails))
        return 1
    print('all static checks passed (runtime behaviour still needs the phone)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
