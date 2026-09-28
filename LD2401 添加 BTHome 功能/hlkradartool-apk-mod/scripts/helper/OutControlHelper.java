package com.hlk.hlkradartool.tool;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Handler;
import android.os.Looper;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.RelativeLayout;
import android.widget.TextView;
import android.widget.Toast;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/**
 * Injected rows for the settings page (activity_set_parameter2):
 *
 * 1. an "OUT 输出控制" block below the photosensitive trigger-level row.  All values hardcoded
 *    from the decoded activity_set_parameter2.xml: rows white with 10dp side padding; title/hint
 *    row 55dp (like rlPhotosensitive1) with the hint in 11sp red; divider 0.5dp #989898 with
 *    10dp side margins; radios use the app default style like rbPhotosensitiveClose.  Sends the
 *    A6 command of the MANUAL_OUT_A6R firmware (0=hold low, 1=hold high, 2=release), sent the
 *    same way the native rows send theirs - a bare write inside the session the page itself opens
 *    in onResume.  No 0x00FF / 0x00FE anywhere: the stock rows never send either from this page.
 *
 * 2. one "BTHome 密钥" row under 控制密码 (addKeyRow) holding both key actions side by side:
 *    label left, value in the middle (starts at 点击获取), and the re-key control at the end.
 *       - tap anywhere on the row except the re-key control -> A6 parameter 3, read the key
 *       - long-press the value -> copy it
 *       - tap the re-key control twice -> A6 parameter 4 (module generates a fresh random key,
 *         firmware 26092424+); it is red and only that control re-keys
 *    A re-key breaks the pairing in Home Assistant, hence the two-tap confirm and the hint line.
 *
 * Interaction rules, fixed on purpose:
 *   - long-press on the key value only ever copies - it never re-keys;
 *   - a tap that reads the key also drops a pending re-key confirm, so "let me look at the key
 *     first" can never be mistaken for the second tap;
 *   - the re-key control is red in every state.
 *
 * Both blocks live in this one class on purpose.  The settings page loads this class already, so a
 * new entry point costs nothing at class-verification time; a class of its own would add a second
 * one at a call site that is not inside any try/catch.
 */
public class OutControlHelper {

    private static final Handler HANDLER = new Handler(Looper.getMainLooper());
    private static final int ROW_ID = 0x4F1B;
    private static final int ROW_ID2 = 0x4F1C;
    private static final int RB_ID = 0x4F20;
    private static final int KEY_ROW_ID = 0x4F2A;
    private static final int KEY_VAL_ID = 0x4F2B;
    private static final String KEY_PLACEHOLDER = "点击获取";
    private static final String KEY_WAITING = "读取中…";
    private static final String KEY_NO_REPLY = "未收到应答";
    private static final String KEY_UNREADABLE = "应答无法识别";
    private static final int KEY_WAIT_MS = 2500;
    private static final int RESET_VAL_ID = 0x4F2E;
    private static final String RESET_IDLE = "点击重置";
    private static final String RESET_ARMED = "再点一次确认";
    private static final String RESET_DONE = "已重置换钥";
    /** The one destructive control on the page, so it is red in every state, not only when armed. */
    private static final int RESET_COLOR = 0xFFFF0000;
    private static final String TAG = "OutControlHelper";

    /** Bumped on every state change, so a stale revert runnable cannot undo a newer one. */
    private static int RESET_TOKEN;

    /** Key seen in the raw frame funnel, waiting for the settings page's A601 event. */
    private static String LAST_KEY;

    /**
     * Called from DemoApplication.parseByData with every complete frame the module sends.
     *
     * Needed because the app keeps no payload for an A6 reply: there is no case for a 20-byte A6
     * frame, so the ReceiveInfo that reaches the settings page has getDataParam() empty (measured:
     * "info: cmd=A601 pay= key=null").  The key therefore comes off the frame itself.  Cost is one
     * toUpperCase + indexOf on a string already in memory, per received frame; frames that are not
     * a key reply return immediately and log nothing.
     */
    public static void onFrame(String frame) {
        if (frame == null) {
            return;
        }
        String up = frame.toUpperCase();
        int at = up.indexOf("A6010000");
        if (at < 0 || up.length() < at + 8 + 32) {
            return;
        }
        LAST_KEY = up.substring(at + 8, at + 8 + 32);
        android.util.Log.i(TAG, "frame carries key: " + LAST_KEY);
    }

    /** Cached getters of ReceiveInfo: the command word and the payload live in two of them. */
    private static Class<?> infoClass;
    private static Method infoCmd;
    private static Method infoPay;

    public static void addTo(final Activity act) {
        try {
            View found = findById(act, "rlFrequent");                 // 触发电平行
            if (found == null) {
                found = findById(act, "rlPhotosensitive2");
            }
            if (found == null || !(found.getParent() instanceof ViewGroup)) {
                return;
            }
            final ViewGroup parent = (ViewGroup) found.getParent();
            if (parent.findViewById(ROW_ID) != null) {
                return; // already added
            }
            int pad = dp(act, 10);

            // ---- divider above: 0.5dp #989898, 10dp side margins (stock spec) ----
            View div = new View(act);
            div.setBackgroundColor(0xFF989898);
            LinearLayout.LayoutParams dp1 = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, px05(act));
            dp1.setMargins(pad, 0, pad, 0);
            div.setLayoutParams(dp1);

            // ---- row A: title + hint, 55dp like rlPhotosensitive1 ----
            LinearLayout rowA = new LinearLayout(act);
            rowA.setId(ROW_ID);
            rowA.setOrientation(LinearLayout.VERTICAL);
            rowA.setGravity(Gravity.CENTER_VERTICAL);
            rowA.setPadding(pad, 0, pad, 0);

            TextView title = new TextView(act);
            title.setText("OUT 输出控制");
            title.setTextColor(0xFF000000);
            rowA.addView(title, new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

            TextView hint = new TextView(act);
            hint.setText("设置后立即生效；重启后恢复自动");
            hint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
            hint.setTextColor(0xFFFF0000);
            rowA.addView(hint, new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

            // ---- row B: radios, wrap like rlPhotosensitive2 ----
            LinearLayout rowB = new LinearLayout(act);
            rowB.setId(ROW_ID2);
            rowB.setOrientation(LinearLayout.HORIZONTAL);
            rowB.setGravity(Gravity.CENTER_VERTICAL);
            rowB.setPadding(pad, 0, pad, 0);

            RadioGroup rg = new RadioGroup(act);
            rg.setOrientation(LinearLayout.HORIZONTAL);
            String[] names = {"低", "高", "自动"};
            for (int i = 0; i < names.length; i++) {
                RadioButton rb = new RadioButton(act);
                rb.setText(names[i]);
                rb.setId(RB_ID + i);
                rg.addView(rb);
                if (i == 2) {
                    rg.check(rb.getId()); // default: released
                }
            }
            rg.setOnCheckedChangeListener(new RadioGroup.OnCheckedChangeListener() {
                @Override
                public void onCheckedChanged(RadioGroup group, int checkedId) {
                    int idx = checkedId - RB_ID;
                    if (idx < 0 || idx > 2) {
                        return;
                    }
                    String val = idx == 0 ? "0000" : (idx == 1 ? "0100" : "0200");
                    // Exactly like the app's own photosensitive / distance rows: one bare write,
                    // sent inline from the click callback.  The page opens the configuration
                    // session itself in onResume (stock code); the old FF -> A6 -> FE sequence
                    // closed that session with its FE, so every later save here (distance, light,
                    // OUT) came back as status 1.
                    send(act, frame("0400", "A600", val));
                }
            });
            rowB.addView(rg, new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

            // ---- placement: divider, rowA, rowB right after the trigger row ----
            int index = parent.indexOfChild(found) + 1;
            parent.addView(div, Math.min(index, parent.getChildCount()));
            parent.addView(rowA, Math.min(index + 1, parent.getChildCount()));
            parent.addView(rowB, Math.min(index + 2, parent.getChildCount()));
        } catch (Throwable t) {
            android.util.Log.e("OutControlHelper", "addTo failed", t);
        }
    }

    // ------------------------------------------------------------------ BTHome key row

    /**
     * The key block under 控制密码, styled off the real views:
     *
     *     BTHome 密钥： 点击获取                               点击重置
     *     重置后模块换新密钥，需在 HA 里重新填写 bindkey
     *
     * The value takes everything between the label and 点击重置, so it starts as the 点击获取
     * affordance and is replaced by the key once it arrives (single line, ellipsised with "..." if
     * it ever does not fit).  点击重置 stays at the tail of that line, red, and the warning sits
     * underneath it as a small red line.
     */
    public static void addKeyRow(final Activity act) {
        try {
            View pwdRow = findById(act, "rlCtrPwd");
            if (pwdRow == null || !(pwdRow.getParent() instanceof LinearLayout)) {
                return;
            }
            final LinearLayout parent = (LinearLayout) pwdRow.getParent();
            if (parent.findViewById(KEY_ROW_ID) != null) {
                return;                                        // already added
            }
            int pad = dp(act, 10);

            View div = new View(act);
            div.setBackgroundColor(colorOf(act, "black_hui", 0xFF989898));
            LinearLayout.LayoutParams dl = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, px05(act));
            dl.setMargins(pad, 0, pad, 0);
            div.setLayoutParams(dl);

            // ---- the row: label + value, with the re-key control at the tail ----
            RelativeLayout row = new RelativeLayout(act);
            row.setId(KEY_ROW_ID);
            row.setGravity(Gravity.CENTER_VERTICAL);
            row.setPadding(pad, 0, pad, 0);

            LinearLayout left = new LinearLayout(act);
            left.setOrientation(LinearLayout.HORIZONTAL);
            left.setGravity(Gravity.CENTER_VERTICAL);

            TextView label = new TextView(act);
            label.setText("BTHome 密钥：");
            copyTextStyle(findById(act, "tvCtrTitle"), label);
            left.addView(label, new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

            final TextView value = new TextView(act);
            value.setId(KEY_VAL_ID);
            value.setText(KEY_PLACEHOLDER);                    // replaced by the key when it arrives
            copyTextStyle(findById(act, "tvpass"), value);     // same style as the password value
            value.setSingleLine(true);
            value.setEllipsize(android.text.TextUtils.TruncateAt.END);
            value.setGravity(Gravity.CENTER_VERTICAL);
            LinearLayout.LayoutParams lpValue = new LinearLayout.LayoutParams(
                    0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f);   // everything up to 点击重置
            lpValue.leftMargin = dp(act, 4);
            left.addView(value, lpValue);

            final TextView reset = new TextView(act);
            reset.setId(RESET_VAL_ID);
            reset.setText(RESET_IDLE);
            styleResetAction(act, reset);
            reset.setGravity(Gravity.CENTER_VERTICAL);
            RelativeLayout.LayoutParams lpReset = new RelativeLayout.LayoutParams(
                    ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lpReset.addRule(RelativeLayout.ALIGN_PARENT_RIGHT);
            lpReset.addRule(RelativeLayout.CENTER_VERTICAL);
            reset.setLayoutParams(lpReset);

            RelativeLayout.LayoutParams lpLeft = new RelativeLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lpLeft.addRule(RelativeLayout.ALIGN_PARENT_LEFT);
            lpLeft.addRule(RelativeLayout.CENTER_VERTICAL);
            lpLeft.addRule(RelativeLayout.LEFT_OF, RESET_VAL_ID);
            left.setLayoutParams(lpLeft);

            value.setOnLongClickListener(new View.OnLongClickListener() {
                @Override
                public boolean onLongClick(View v) {
                    return copyIfKey(act);            // long-press only ever copies
                }
            });
            // The value needs its own click listener: a long-clickable child swallows the tap.
            // While it shows 点击获取 (or a status word) a tap asks for the key; once the key is
            // there a tap does nothing - re-fetching on every tap was the thing to avoid.
            value.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    if (hasKey(act)) {
                        return;
                    }
                    disarmReset(act);
                    requestKey(act);
                }
            });
            reset.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    onResetClick(act);       // the only control that may re-key
                }
            });

            row.addView(left);
            row.addView(reset);
            // the row itself stays un-clickable on purpose: no hidden fetch anywhere on the line

            // ---- the warning line under it ----
            TextView hint = new TextView(act);
            hint.setText("重置后模块换新密钥，需在 HA 里重新填写 bindkey");
            hint.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
            hint.setTextColor(0xFFFF0000);
            hint.setPadding(pad, 0, pad, dp(act, 6));
            hint.setLayoutParams(new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

            int index = Math.min(parent.indexOfChild(pwdRow) + 1, parent.getChildCount());
            LinearLayout.LayoutParams rl = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, dp(act, 40));
            rl.topMargin = dp(act, 1);                          // same as rlCtrPwd above
            row.setLayoutParams(rl);

            // divider, the row, the warning, above whatever rows (lypass and friends) follow rlCtrPwd
            parent.addView(div, index);
            parent.addView(row, Math.min(index + 1, parent.getChildCount()));
            parent.addView(hint, Math.min(index + 2, parent.getChildCount()));
        } catch (Throwable t) {
            android.util.Log.e(TAG, "addKeyRow failed", t);
        }
    }

    private static void onResetClick(final Activity act) {
        try {
            final TextView action = act.findViewById(RESET_VAL_ID);
            String text = action == null ? "" : String.valueOf(action.getText());
            if (RESET_ARMED.equals(text)) {
                armReset(act, action, RESET_DONE);
                requestReset(act);
            } else if (!RESET_DONE.equals(text)) {
                armReset(act, action, RESET_ARMED);
            }
        } catch (Throwable t) {
            android.util.Log.w(TAG, "reset click", t);
        }
    }

    /** True while the row is showing an actual 16-byte key (not a placeholder or a status word). */
    private static boolean hasKey(Activity act) {
        TextView value = act.findViewById(KEY_VAL_ID);
        return value != null && String.valueOf(value.getText()).matches("(?i)[0-9A-F]{32}");
    }

    /** Long-press on a displayed key copies it.  False when there is nothing to copy. */
    private static boolean copyIfKey(Activity act) {
        TextView value = act.findViewById(KEY_VAL_ID);
        String text = value == null ? "" : String.valueOf(value.getText());
        if (!text.matches("(?i)[0-9A-F]{32}")) {
            return false;
        }
        android.util.Log.i(TAG, "copy: " + text);
        copyToClipboard(act, text);
        return true;
    }

    /** Size and typeface follow the stock value beside it; the colour is always the danger red. */
    private static void styleResetAction(Activity act, TextView action) {
        copyTextStyle(findById(act, "tvpass"), action);
        action.setTextColor(RESET_COLOR);
    }

    /** A tap on the key row means "show me the key", not "go ahead": drop a pending confirm. */
    private static void disarmReset(Activity act) {
        TextView action = act.findViewById(RESET_VAL_ID);
        if (action == null || !RESET_ARMED.equals(String.valueOf(action.getText()))) {
            return;
        }
        action.setText(RESET_IDLE);
        action.setTextColor(RESET_COLOR);
        ++RESET_TOKEN;                                 // the pending revert is now stale
    }

    /** Shows the state in red and reverts to 点击重置 later, unless a newer state replaced it. */
    private static void armReset(final Activity act, final TextView action, final String state) {
        if (action != null) {
            action.setText(state);
            action.setTextColor(RESET_COLOR);
        }
        final int token = ++RESET_TOKEN;
        HANDLER.postDelayed(new Runnable() {
            @Override
            public void run() {
                if (token != RESET_TOKEN) {
                    return;
                }
                TextView a = act.findViewById(RESET_VAL_ID);
                if (a == null || !state.equals(String.valueOf(a.getText()))) {
                    return;
                }
                a.setText(RESET_IDLE);
                styleResetAction(act, a);
            }
        }, RESET_DONE.equals(state) ? 3000 : 5000);
    }

    /**
     * Ask the module to generate and store a fresh bindkey: A6 parameter 4, one bare write like the
     * key request (no 0x00FF / 0x00FE - see requestKey).  It answers in the same A601 shape as
     * parameter 3, so onInfo paints the new key.  Nothing follows it up: firmware older than
     * 26092424 rejects parameter 4, and in that case the key row is better left showing
     * 点击获取 - a read-back would only re-display the old, unchanged key under a "已重置换钥" label.
     */
    private static void requestReset(final Activity act) {
        setKeyText(act, KEY_WAITING);
        android.util.Log.i(TAG, "reset: sending A600/0400");
        send(act, frame("0400", "A600", "0400"));
        expectReply(act);
    }

    /**
     * Ask the module for the BTHome bindkey.  A6 parameter 3, sent as one bare write from the
     * click callback - the same shape as the stock distance / light rows: the page opens the
     * configuration session itself in onResume, so nothing here sends 0x00FF, and nothing on this
     * page ever sends 0x00FE (that closes the session for the rest of the page's life).
     *
     * One frame per tap, no timer-driven retry, but the row reports what happened instead of
     * sitting on 点击获取 in silence: 读取中… -> the key, or 未收到应答 / 应答无法识别.
     */
    private static void requestKey(final Activity act) {
        setKeyText(act, KEY_WAITING);
        android.util.Log.i(TAG, "key: sending A600/0300");
        send(act, frame("0400", "A600", "0300"));
        expectReply(act);
    }

    /** UI-only countdown; sends nothing.  If a reply replaced 读取中…, this does not fire. */
    private static void expectReply(final Activity act) {
        HANDLER.postDelayed(new Runnable() {
            @Override
            public void run() {
                TextView v = act.findViewById(KEY_VAL_ID);
                if (v != null && KEY_WAITING.contentEquals(v.getText())) {
                    v.setText(KEY_NO_REPLY);
                    android.util.Log.i(TAG, "no reply to the key request");
                }
            }
        }, KEY_WAIT_MS);
    }

    private static void setKeyText(Activity act, String text) {
        TextView value = act.findViewById(KEY_VAL_ID);
        if (value != null) {
            value.setText(text);
        }
    }

    /**
     * Called from the top of SetParameter2Activity.onReceiveInfoMessage with the ReceiveInfo.
     * Display only: it never touches that method's control flow, so nothing here can take the
     * settings page down.
     *
     * The reply lands in two halves: getStrParam() holds the command word ("A601") and
     * getDataParam() the rest of the frame.  A6 replies are parameter frames, so the app sends
     * them down its "参数 + 设置失败" branch and they never reach its ACK compare chain -
     * injecting there is why earlier attempts never fired.
     *
     * findKey() does the reading (see keyIn for the anchor rule); every String getter is tried if
     * the payload one comes up empty, and every frame that reaches this method is logged, so a
     * reply that fails to display can be diagnosed from logcat alone.  The row also reports the
     * outcome itself: the key, or 未收到应答 / 应答无法识别.
     */
    public static void onInfo(Activity act, Object info) {
        try {
            if (info == null) {
                return;
            }
            String cmd = null;
            String pay = null;
            if (readPair(info)) {
                cmd = (String) infoCmd.invoke(info);
                pay = (String) infoPay.invoke(info);
            }
            String key = findKey(info, pay, cmd);
            if (key == null && String.valueOf(cmd).trim().toUpperCase().startsWith("A6")) {
                // The app drops A6 payloads, so fall back to the key taken off the frame funnel;
                // onFrame() ran for the very frame this event is about.
                key = LAST_KEY;
                LAST_KEY = null;
            }
            android.util.Log.i(TAG, "info: cmd=" + cmd + " pay=" + pay + " key=" + key);
            if (key == null) {
                // An A6 reply we could not read: say so, but only while the row is waiting for a
                // key, so the OUT block's own A6 echo cannot repaint this row.
                TextView v = act.findViewById(KEY_VAL_ID);
                if (v != null && KEY_WAITING.contentEquals(v.getText())
                        && String.valueOf(cmd).trim().toUpperCase().startsWith("A6")) {
                    v.setText(KEY_UNREADABLE);
                }
                return;
            }
            TextView value = act.findViewById(KEY_VAL_ID);
            if (value != null) {
                value.setText(key);
            } else {
                Toast.makeText(act, "BTHome 密钥: " + key, Toast.LENGTH_LONG).show();
            }
        } catch (Throwable t) {
            android.util.Log.w(TAG, "onInfo", t);
        }
    }

    /** Hex digits only, upper case - the payload arrives as an ASCII hex string. */
    private static String hexOf(String s) {
        return s == null ? "" : s.replaceAll("[^0-9A-Fa-f]", "").toUpperCase();
    }

    /**
     * The 32 hex digits of the bindkey in this frame, or null when it is not an A6 key reply.
     *
     * getDataParam() holds the reply but the split is not the same for every shape, so a candidate
     * is accepted when it carries at least 16 bytes with the reply header (a6 01 00 00) or the A6
     * command word in front of it.  That covers the two shapes seen so far:
     *
     *     a6010000c500c1dbb41150535c26341be7692d2f     (whole reply captured on the wire)
     *     c500c1dbb41150535c26341be7692d2f             (payload only)
     *
     * and still rejects a 2-byte OUT echo (a60100000200 -> 2 bytes after the header).  If the
     * payload getter turns out to hold something else on a given app build, every no-arg String
     * getter is tried before giving up, and the winner is visible in logcat.
     */
    private static String findKey(Object info, String pay, String cmd) {
        String word = String.valueOf(cmd).trim().toUpperCase();
        String key = keyIn(pay, word);
        if (key != null) {
            return key;
        }
        List<String> rest = new ArrayList<String>();
        try {
            for (Method m : info.getClass().getMethods()) {
                if (m.getParameterTypes().length != 0 || m.getReturnType() != String.class) {
                    continue;
                }
                Object v = m.invoke(info);
                if (v instanceof String) {
                    rest.add((String) v);
                }
            }
        } catch (Throwable ignored) {
        }
        for (String cand : rest) {
            key = keyIn(cand, word);
            if (key != null) {
                android.util.Log.i(TAG, "key found in another getter: " + cand);
                return key;
            }
        }
        return null;
    }

    /**
     * The 32 hex digits of the bindkey in this frame, or null when it is not an A6 key reply.
     *
     * The reply read straight off the module's UART on 2026-09-28 (firmware 26092424) is
     *
     *     a6010000 f076b1fc19fd86ff85e7ccfbbdd258f3
     *     cmd      status | 16-byte key
     *
     * so the anchor is the 8 hex digit header "A6010000" and the key is the 32 digits right after
     * it.  One rule covers every wrapper the app may hand us - payload alone, command + payload, or
     * the whole fdfcfbfa..04030201 frame - where "take the last 32 digits" would pick up a trailing
     * 04030201 and drop key bytes.  Without an anchor only a bare 32 digit payload is accepted, and
     * then only when the A6 command word came along too.
     */
    private static String keyIn(String cand, String word) {
        String raw = hexOf(cand);
        if (raw.isEmpty()) {
            return null;
        }
        int at = raw.lastIndexOf("A6010000");
        if (at >= 0 && raw.length() >= at + 8 + 32) {
            return raw.substring(at + 8, at + 8 + 32);
        }
        if (raw.length() == 32 && (word.startsWith("A6") || raw.startsWith("A6"))) {
            return raw;                                        // payload on its own
        }
        return null;
    }

    /** Resolves and caches the two String getters; falls back to a scan if the names ever change. */
    private static boolean readPair(Object info) {
        Class<?> c = info.getClass();
        if (c == infoClass && infoCmd != null && infoPay != null) {
            return true;
        }
        try {
            infoCmd = c.getMethod("getStrParam");
            infoPay = c.getMethod("getDataParam");
            infoClass = c;
            return true;
        } catch (Throwable ignored) {
        }
        Method cmd = null;
        Method pay = null;
        try {
            for (Method m : c.getMethods()) {
                if (m.getParameterTypes().length != 0 || m.getReturnType() != String.class) {
                    continue;
                }
                Object v = m.invoke(info);
                if (!(v instanceof String)) {
                    continue;
                }
                if ("A601".equalsIgnoreCase(((String) v).trim())) {
                    cmd = m;
                } else if (pay == null && ((String) v).matches("(?i)[0-9a-f]{32,}")) {
                    pay = m;
                }
            }
        } catch (Throwable t) {
            return false;
        }
        if (cmd == null || pay == null) {
            return false;
        }
        infoClass = c;
        infoCmd = cmd;
        infoPay = pay;
        return true;
    }

    private static void copyToClipboard(Activity act, String text) {
        try {
            ClipboardManager cm = (ClipboardManager) act.getSystemService(Context.CLIPBOARD_SERVICE);
            if (cm != null) {
                cm.setPrimaryClip(ClipData.newPlainText("BTHome 密钥", text));
                Toast.makeText(act, "已复制", Toast.LENGTH_SHORT).show();
            }
        } catch (Throwable t) {
            android.util.Log.w(TAG, "copy failed", t);
        }
    }

    private static void copyTextStyle(View src, TextView dst) {
        try {
            if (!(src instanceof TextView)) {
                return;
            }
            TextView s = (TextView) src;
            dst.setTextSize(TypedValue.COMPLEX_UNIT_PX, s.getTextSize());
            dst.setTextColor(s.getTextColors());
            dst.setTypeface(s.getTypeface());
        } catch (Throwable ignored) {
        }
    }

    private static int colorOf(Activity act, String name, int fallback) {
        try {
            int id = act.getResources().getIdentifier(name, "color", act.getPackageName());
            if (id != 0) {
                return act.getResources().getColor(id);
            }
        } catch (Throwable ignored) {
        }
        return fallback;
    }

    private static int px05(Activity act) {
        return Math.max(1, Math.round(0.5f * act.getResources().getDisplayMetrics().density));
    }

    private static int dp(Activity act, int v) {
        return (int) (v * act.getResources().getDisplayMetrics().density);
    }

    private static View findById(Activity a, String name) {
        int id = a.getResources().getIdentifier(name, "id", a.getPackageName());
        return id == 0 ? null : a.findViewById(id);
    }

    private static String frame(String len, String cmd, String val) {
        return "FDFCFBFA" + len + cmd + val + "04030201";
    }

    private static void send(Activity act, String frame) {
        try {
            Class<?> ble = Class.forName("com.hlk.hlkradartool.activity.BLEListActivity");
            Object inst = ble.getMethod("getInstance").invoke(null);
            String mac = macOf(act);
            if (inst == null || mac == null) {
                return;
            }
            ble.getMethod("sendDataByMAC", String.class, String.class).invoke(inst, mac, frame);
        } catch (Throwable t) {
            // ignore
        }
    }

    private static String macOf(Activity act) {
        try {
            Class<?> appCls = Class.forName("com.hlk.hlkradartool.activity.DemoApplication");
            Object app = appCls.getMethod("getInstance").invoke(null);
            Object sel = appCls.getField("nowSelectDevice").get(app);
            return (String) sel.getClass().getMethod("getMACAddress").invoke(sel);
        } catch (Throwable t) {
            return null;
        }
    }
}
