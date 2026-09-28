# -*- coding: utf-8 -*-
"""Keep the complete frame in reach of OutControlHelper (2026-09-28).

The settings page cannot see a bindkey reply's payload: the app has no case for a 20-byte A6
frame, so the ReceiveInfo it dispatches carries only the command word (measured on the phone:
"OutControlHelper: info: cmd=A601 pay= key=null"), and getDataParam() is empty for the ACK class
of frames in general.

The complete frame does exist, as a hex string, in DemoApplication.parseByData(String mac,
String raw, String model) - the app's single data funnel - in local v0 right after the substring
that cuts the frame out of the receive buffer.  This inserts one void static call there:

    invoke-static {v0}, ...OutControlHelper->onFrame(Ljava/lang/String;)V

Same technique as the other hooks: a single invoke, no move-result, no branch, no label change,
and v0 keeps its value because invoke-static does not write its arguments.

Run after patch_bthome_key.py.  Idempotent.
"""
from pathlib import Path

APK = Path(r'C:\AgentWorkspace\LD24\apk')
ACT = APK / 'tree' / 'smali_classes2' / 'com' / 'hlk' / 'hlkradartool' / 'activity'
APP = ACT / 'DemoApplication.smali'

METHOD = '.method public parseByData(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V'
# The LD2401 dispatch: v0 holds the complete frame sliced out of the receive buffer (the same
# string the app logs as "接收蓝牙有效数据").  The substring that builds v0 appears four times in
# parseByData (one per branch), so this call site - not that instruction - is the unique anchor.
ANCHOR = ('    invoke-virtual {v1, p1, v0, p3}, Lcom/hlk/hlkradartool/data/DataAnalysisHelper;'
          '->startDataAnalysis(Ljava/lang/String;Ljava/lang/String;Ljava/lang/String;)V\n')
CALL = ('    invoke-static {v0}, Lcom/hlk/hlkradartool/tool/OutControlHelper;'
        '->onFrame(Ljava/lang/String;)V\n\n')


def main():
    t = APP.read_text(encoding='utf-8')

    if 'OutControlHelper;->onFrame' in t:
        print('1. frame hook already present')
    else:
        assert t.count(ANCHOR) == 1, 'LD2401 dispatch anchor not unique: %d' % t.count(ANCHOR)
        t = t.replace(ANCHOR, CALL + ANCHOR, 1)
        APP.write_text(t, encoding='utf-8')
        print('1. frame hook inserted before the LD2401 dispatch')

    t = APP.read_text(encoding='utf-8')
    assert t.count('OutControlHelper;->onFrame') == 1, 'frame hook count != 1'
    assert t.count('OutControlHelper;') == 1, 'unexpected extra OutControlHelper reference'
    i = t.index(METHOD)
    assert 'OutControlHelper;->onFrame' in t[i:i + 8000], 'hook landed outside parseByData'
    j = t.index(ANCHOR)
    assert t[j - 200:j].rstrip().endswith('Ljava/lang/String;') or 'move-result-object v1' in t[j - 200:j], \
        'anchor context is not the dispatch call'
    print('checks: onFrame=1 in parseByData, right before startDataAnalysis, no other refs')


if __name__ == '__main__':
    main()
