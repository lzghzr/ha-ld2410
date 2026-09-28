# -*- coding: utf-8 -*-
"""The BTHome-key row on the settings page (same shape as 控制密码, no chevron).

Two entry points in SetParameter2Activity, both landing in OutControlHelper - the helper class
the page already loads, so no new class has to be verified at a call site that sits outside any
try/catch:

  1. init(): OutControlHelper.addKeyRow(this) right after the OUT block call.  Builds the row
     under rlCtrPwd; tapping it asks the module for the derived bindkey (A6 parameter 3) and puts
     the 32 hex characters where "点击获取" was; long-press copies them.

  2. the TOP of onReceiveInfoMessage: OutControlHelper.onInfo(this, info).  It must be here, not
     in the ACK compare chain, for two reasons:
       - the app splits on ReceiveInfo.getBlParam() before that chain, and an A6 reply is a
         parameter frame, so it never reaches the chain at all;
       - the payload lives in ReceiveInfo.getDataParam(); getStrParam() holds only "A601".
     onInfo() returns void and takes no branch: the frame then continues through the stock code
     untouched.  An earlier version jumped to the method's cleanup label on a match, which put a
     join point in the middle of the method (registers typed differently on the two paths) and
     is one of the suspects for the crash on entering the page.

Run after patch_a601_popup.py.  Idempotent (a second run reports and skips).
"""
import shutil
from pathlib import Path

APK = Path(r'C:\AgentWorkspace\LD24\apk')
ACT = APK / 'tree' / 'smali_classes2' / 'com' / 'hlk' / 'hlkradartool' / 'activity'
TOOL = APK / 'tree' / 'smali_classes2' / 'com' / 'hlk' / 'hlkradartool' / 'tool'

PAGE = ACT / 'SetParameter2Activity.smali'
ADD_AFTER = ('    invoke-static {p0}, Lcom/hlk/hlkradartool/tool/OutControlHelper;'
             '->addTo(Landroid/app/Activity;)V\n')
ADD_LINE = ('    invoke-static {p0}, Lcom/hlk/hlkradartool/tool/OutControlHelper;'
            '->addKeyRow(Landroid/app/Activity;)V\n')

METHOD_HEAD = ('    .annotation runtime Lorg/greenrobot/eventbus/Subscribe;\n'
               '        threadMode = .enum Lorg/greenrobot/eventbus/ThreadMode;->MAIN:'
               'Lorg/greenrobot/eventbus/ThreadMode;\n'
               '    .end annotation\n')
ENTRY_PATCH = (METHOD_HEAD + '\n'
               '    invoke-static {p0, p1}, Lcom/hlk/hlkradartool/tool/OutControlHelper;'
               '->onInfo(Landroid/app/Activity;Ljava/lang/Object;)V\n')


def main():
    t = PAGE.read_text(encoding='utf-8')
    assert 'BtKeyHelper' not in t, 'tree still carries the withdrawn BtKeyHelper injection'

    if 'OutControlHelper;->onInfo' in t:
        print('1. entry hook already present')
    else:
        assert t.count(METHOD_HEAD) == 1, 'method head anchor not unique'
        t = t.replace(METHOD_HEAD, ENTRY_PATCH, 1)
        PAGE.write_text(t, encoding='utf-8')
        print('1. display-only entry hook inserted')

    t = PAGE.read_text(encoding='utf-8')
    if 'OutControlHelper;->addKeyRow' in t:
        print('2. addKeyRow already present')
    else:
        assert t.count(ADD_AFTER) == 1, 'OutControlHelper.addTo injection point not unique'
        t = t.replace(ADD_AFTER, ADD_AFTER + ADD_LINE, 1)
        PAGE.write_text(t, encoding='utf-8')
        print('2. addKeyRow injected after the OUT block call')

    c = PAGE.read_text(encoding='utf-8')
    assert c.count('OutControlHelper;->onInfo') == 1
    assert c.count('OutControlHelper;->addKeyRow') == 1
    assert c.count('OutControlHelper;->addTo') == 1
    i = c.index('OutControlHelper;->onInfo')
    assert '.line 1624' in c[i:i + 400], 'the hook must run before the stock body'
    for bad in ('BtKeyHelper', 'cond_keydone', 'cond_keyni', 'cond_a6hint', '"A603"'):
        assert bad not in c, 'stale ' + bad

    # the withdrawn class must not exist anywhere in the tree
    for p in TOOL.glob('BtKeyHelper*.smali'):
        p.unlink()
    assert not list(TOOL.glob('BtKeyHelper*.smali')), 'BtKeyHelper.smali left in the tree'
    print('checks: onInfo=1 addKeyRow=1 addTo=1, no leftover label / branch / BtKeyHelper')


if __name__ == '__main__':
    main()
