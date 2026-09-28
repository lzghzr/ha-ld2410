# -*- coding: utf-8 -*-
"""Show the native 设置成功 hint for the A6 (OUT control) ACK.

SetParameter2Activity.onReceiveInfoMessage dispatches ACKs by comparing the received frame
text against the ACK command words (FF01, FE01, 6001, 6401, A901, AA01, A101, AD01, B801,
B301, 6101, A001, AB01, AE01, D301).  There is no A601 branch, so the OUT control's ACK was
silently dropped and the block never showed a popup.

This inserts an A601 branch that shows the same AreaConfirmWindowHint(shezhi_chenggong) the
native rows use, and rewires the preceding (A101) branch's mismatch target so the new branch
is actually reached.  Order matters: rewire first (count=1), then insert - a plain
str.replace would also rewrite the inserted block's own fall-through.

Runs once on a fresh patched tree; asserts if the branch is already there.
"""
from pathlib import Path

PATH = Path(r'C:\AgentWorkspace\LD24\apk\tree\smali_classes2\com\hlk\hlkradartool'
            r'\activity\SetParameter2Activity.smali')
ANCHOR = '    :cond_c\n    const-string v0, "AD01"\n'
MISMATCH = '    if-eqz v0, :cond_c\n'
BLOCK = '''    :cond_a6
    const-string v0, "A601"
    invoke-virtual {p1, v0}, Ljava/lang/String;->equalsIgnoreCase(Ljava/lang/String;)Z
    move-result v0
    if-eqz v0, :cond_c
    iget-object p1, p0, Lcom/hlk/hlkradartool/activity/SetParameter2Activity;->areaConfirmWindowHint:Lcom/hlk/hlkradartool/view/AreaConfirmWindowHint;
    sget v0, Lcom/hlk/hlkradartool/R$string;->shezhi_chenggong:I
    invoke-virtual {p0, v0}, Lcom/hlk/hlkradartool/activity/SetParameter2Activity;->getString(I)Ljava/lang/String;
    move-result-object v0
    invoke-virtual {p1, v0}, Lcom/hlk/hlkradartool/view/AreaConfirmWindowHint;->setMsgAndShow(Ljava/lang/String;)V
    goto/16 :goto_0

'''


def main():
    src = PATH.read_text(encoding='utf-8')
    assert '"A601"' not in src, 'A601 branch already present'
    assert src.count(ANCHOR) == 1, 'AD01 anchor not unique'
    assert src.count(MISMATCH) == 1, 'wrong number of `if-eqz v0, :cond_c` branches'

    src = src.replace(MISMATCH, '    if-eqz v0, :cond_a6\n', 1)   # 1. rewire A101
    src = src.replace(ANCHOR, BLOCK + ANCHOR, 1)                  # 2. insert the branch
    PATH.write_text(src, encoding='utf-8')

    check = PATH.read_text(encoding='utf-8')
    assert check.count('"A601"') == 1
    assert check.count(':cond_a6') == 2                    # label + the rewired branch
    assert check.count('    if-eqz v0, :cond_c\n') == 1     # the new branch's fall-through
    print('A601 -> shezhi_chenggong branch inserted (A601=%d, cond_a6=%d)'
          % (check.count('"A601"'), check.count(':cond_a6')))


if __name__ == '__main__':
    main()
