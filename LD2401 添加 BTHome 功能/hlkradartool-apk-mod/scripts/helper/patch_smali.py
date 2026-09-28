# -*- coding: utf-8 -*-
"""Smali patches for HLKRadarTool 1.6.112 (custom firmware + LD2401 light UI).

Run on a FRESH apktool decode of the stock APK (hlk_apk). All patches are
idempotence-checked with asserts; re-running on a patched tree will fail.

Patches:
1. VersionListActivity: 自定义固件升级 button + onActivityResult → the helper
   copies the picked .ufw to the firmware cache, fakes FirmwareInfoBean and
   launches NewOTAInfoActivityV2 (firmwareCode=2); the stock V2 flow then
   flashes it from the cache-hit path (no network, no server info).
2. ControlBLEActivity: remove the HLK-LD2401_ name filter that hides the
   photosensitive chart.
3. SetParameter2Activity: keep the photosensitive settings rows visible for
   LD2401; AD01 ACK no longer prompts a reboot.
4. OutControlHelper (companion class) injects the OUT-control block into the
   settings page; CustomFwHelper provides the picker/copy logic.
"""
import shutil
from pathlib import Path

APK_DIR = Path(r'C:\AgentWorkspace\LD24\apk\tree')
SMALI2 = APK_DIR / 'smali_classes2'
ACT_DIR = SMALI2 / 'com' / 'hlk' / 'hlkradartool' / 'activity'
TOOL_DIR = SMALI2 / 'com' / 'hlk' / 'hlkradartool' / 'tool'
HELPER_DIR = Path(r'C:\AgentWorkspace\LD24\apk\helper\out_smali\com\hlk\hlkradartool\tool')


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def patch_versionlist():
    """自定义固件升级 button + onActivityResult in VersionListActivity."""
    path = ACT_DIR / 'VersionListActivity.smali'
    t = read(path)
    assert 'addVersionEntryButton' not in t, 'already patched'
    assert 'onActivityResult' not in t, 'already has onActivityResult'

    anchor = 'invoke-virtual {v0, p0}, Landroid/widget/Button;->setOnClickListener(Landroid/view/View$OnClickListener;)V'
    i = t.find('R$id;->btnStart')
    assert i > 0, 'btnStart not found'
    j = t.index(anchor, i)
    k = t.index('\n', j) + 1
    ins = ('\n    invoke-static {p0}, Lcom/hlk/hlkradartool/tool/CustomFwHelper;'
           '->addVersionEntryButton(Landroid/app/Activity;)V\n')
    t = t[:k] + ins + t[k:]

    onact = '''
.method protected onActivityResult(IILandroid/content/Intent;)V
    .locals 1

    const/16 v0, 0x4f1a

    if-ne p1, v0, :cond_fw_super

    const/4 v0, -0x1

    if-ne p2, v0, :cond_fw_super

    if-eqz p3, :cond_fw_super

    invoke-static {p0, p3}, Lcom/hlk/hlkradartool/tool/CustomFwHelper;->handleVersionPick(Landroid/app/Activity;Landroid/content/Intent;)Z

    move-result v0

    if-eqz v0, :cond_fw_super

    return-void

    :cond_fw_super
    invoke-super {p0, p1, p2, p3}, Landroidx/appcompat/app/AppCompatActivity;->onActivityResult(IILandroid/content/Intent;)V

    return-void
.end method
'''
    t = t.rstrip('\n') + '\n' + onact
    write(path, t)
    print('patched VersionListActivity')


def patch_light_filter():
    """ControlBLEActivity: show the photosensitive chart for LD2401 too."""
    path = ACT_DIR / 'ControlBLEActivity.smali'
    t = read(path)
    anchor = '''    const-string v4, "HLK-LD2401_"

    invoke-virtual {v1, v4}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v1

    if-nez v1, :cond_1'''
    assert t.count(anchor) == 1, 'light filter anchor'
    t = t.replace(anchor, anchor.replace('if-nez v1, :cond_1', 'nop'))
    write(path, t)
    print('patched ControlBLEActivity light filter')


def patch_light_settings():
    """SetParameter2Activity: photosensitive settings stay visible for LD2401."""
    path = ACT_DIR / 'SetParameter2Activity.smali'
    t = read(path)
    anchor = '''    const-string v1, "HLK-LD2401_"

    invoke-virtual {v0, v1}, Ljava/lang/String;->contains(Ljava/lang/CharSequence;)Z

    move-result v0

    if-eqz v0, :cond_3'''
    assert t.count(anchor) == 1, 'light settings anchor'
    t = t.replace(anchor, anchor.replace('if-eqz v0, :cond_3', 'goto/16 :cond_3'))
    write(path, t)
    print('patched SetParameter2Activity light settings hide')


def patch_ad01_no_reboot():
    """SetParameter2Activity: AD01 ACK shows plain 设置成功 (no reboot prompt)."""
    path = ACT_DIR / 'SetParameter2Activity.smali'
    t = read(path)
    i = t.find('const-string v0, "AD01"')
    assert i > 0, 'AD01 not found'
    start_marker = 'if-eqz v0, :cond_d'
    j = text_index(t, start_marker, i)
    k = t.index('goto :goto_0', t.index('isRestart:Z', j))
    k = t.index('\n', k) + 1
    replacement = '''if-eqz v0, :cond_d

    iget-object p1, p0, Lcom/hlk/hlkradartool/activity/SetParameter2Activity;->areaConfirmWindowHint:Lcom/hlk/hlkradartool/view/AreaConfirmWindowHint;

    sget v0, Lcom/hlk/hlkradartool/R$string;->shezhi_chenggong:I

    invoke-virtual {p0, v0}, Lcom/hlk/hlkradartool/activity/SetParameter2Activity;->getString(I)Ljava/lang/String;

    move-result-object v0

    invoke-virtual {p1, v0}, Lcom/hlk/hlkradartool/view/AreaConfirmWindowHint;->setMsgAndShow(Ljava/lang/String;)V

    goto/16 :goto_0
'''
    t = t[:j] + replacement + t[k:]
    write(path, t)
    print('patched AD01 no-reboot')


def text_index(t, sub, frm):
    return t.index(sub, frm)




def patch_out_control_entry():
    """SetParameter2Activity: call OutControlHelper.addTo(this) in init() so the
    OUT-control block is injected into the settings page."""
    path = ACT_DIR / 'SetParameter2Activity.smali'
    t = read(path)
    assert 'OutControlHelper' not in t, 'already patched'
    anchor = 'invoke-virtual {v0, p0}, Landroid/view/View;->setOnClickListener(Landroid/view/View$OnClickListener;)V'
    i = t.find('R$id;->btnPhotosensitive')
    assert i > 0, 'btnPhotosensitive not found'
    j = t.index(anchor, i)
    k = t.index('\n', j) + 1
    ins = '    invoke-static {p0}, Lcom/hlk/hlkradartool/tool/OutControlHelper;->addTo(Landroid/app/Activity;)V\n'
    t = t[:k] + ins + t[k:]
    write(path, t)
    print('patched OUT control entry')


def copy_helpers():
    TOOL_DIR.mkdir(parents=True, exist_ok=True)
    for f in HELPER_DIR.glob('*.smali'):
        shutil.copyfile(f, TOOL_DIR / f.name)
    print('helpers copied:', [f.name for f in TOOL_DIR.glob('CustomFw*.smali')] +
          [f.name for f in TOOL_DIR.glob('OutControl*.smali')])


def main():
    patch_versionlist()
    patch_light_filter()
    patch_light_settings()
    patch_ad01_no_reboot()
    patch_out_control_entry()
    copy_helpers()


if __name__ == '__main__':
    main()
