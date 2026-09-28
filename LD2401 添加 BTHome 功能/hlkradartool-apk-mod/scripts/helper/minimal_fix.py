# -*- coding: utf-8 -*-
"""Minimal fix: keep the OUT-control block but make it send only the A6 frame, and undo the
funnel-wide SessionHelper patch (which is what made the page laggy).

The app opens the configuration session on the control page (FF) and closes it on the way
out (FE).  SetParameter2Activity - the page carrying 距离/光敏/OUT - never sends FF/FE itself,
so it relies on that session.  The injected OUT block used to send FF -> A6 -> FE, and its FE
closed the session, after which every save on the page (including the OUT row) answered
status 1 = 设置失败.  Sending A6 alone is exactly what the app's own rows do.
"""
import shutil
from pathlib import Path

HELPER = Path(r'C:\AgentWorkspace\LD24\apk\helper')
TREE = Path(r'C:\AgentWorkspace\LD24\apk\tree')
SMALI2 = TREE / 'smali_classes2'
ACT = SMALI2 / 'com' / 'hlk' / 'hlkradartool' / 'activity'
TOOL = SMALI2 / 'com' / 'hlk' / 'hlkradartool' / 'tool'

# 1. install the A6-only OutControlHelper smali (it also carries the BTHome-key row)
src = HELPER / 'out_oc_smali' / 'com' / 'hlk' / 'hlkradartool' / 'tool'
names = tuple(sorted(p.name for p in src.glob('OutControlHelper*.smali')))
assert len(names) >= 3, 'OutControlHelper smali missing: ' + str(src)
for n in names:
    shutil.copyfile(src / n, TOOL / n)
# the frame constants live in the inner classes ($1 = the radio listener), so check the set
oc = {n: (TOOL / n).read_text(encoding='utf-8') for n in names}
assert any('A600' in t for t in oc.values()), 'A6 frame missing'
assert not any('FE00' in t for t in oc.values()), 'FE frame still present in the OUT block'
assert any('addKeyRow' in t for t in oc.values()), 'key row missing'
assert any('onInfo' in t for t in oc.values()), 'key hook missing'
print('1. OutControlHelper replaced (A6 only, no FF/FE, plus the BTHome-key row)')

# 2. remove the funnel-wide SessionHelper patch
helper = TOOL / 'SessionHelper.smali'
if helper.exists():
    helper.unlink()
    print('2a. SessionHelper.smali removed from the tree')
ble = ACT / 'BLEListActivity.smali'
s = ble.read_text(encoding='utf-8')
call = ('\n    invoke-static {p1, p2}, Lcom/hlk/hlkradartool/tool/SessionHelper;'
        '->ensure(Ljava/lang/String;Ljava/lang/String;)V\n')
if call in s:
    s = s.replace(call, '')
    ble.write_text(s, encoding='utf-8')
    print('2b. injected call removed from BLEListActivity.sendDataByMAC')
assert 'SessionHelper' not in ble.read_text(encoding='utf-8')

# 3. nothing else may mention the removed helper
leftovers = [str(p) for p in SMALI2.rglob('*.smali')
             if 'SessionHelper' in p.read_text(encoding='utf-8')]
assert not leftovers, leftovers[:5]
print('3. no SessionHelper references left anywhere')

# 4. the rest of the modifications must still be intact
joined = '\n'.join(p.read_text(encoding='utf-8') for p in ACT.glob('*.smali'))
for must in ('addVersionEntryButton', 'handleVersionPick', 'OutControlHelper;->addTo'):
    assert must in joined, 'lost ' + must
assert 'addPickButton' not in joined, 'stale addPickButton came back'
print('4. earlier patches intact (custom firmware entry, OUT block, light visibility)')
