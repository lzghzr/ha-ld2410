package com.hlk.hlkradartool.tool;

import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.provider.OpenableColumns;
import android.util.Log;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Custom firmware upgrade entry for VersionListActivity (local modification).
 * Flow: tap 自定义固件升级 → system file picker → the picked .ufw is copied to
 * the app firmware cache as custom.ufw and a fake FirmwareInfoBean is placed in
 * VersionListActivity.selectVersion → the stock NewOTAInfoActivityV2
 * (firmwareCode=2) flow then flashes it from the cache-hit path with no network
 * access; that page shows only 开始升级.
 */
public class CustomFwHelper {

    private static final String TAG = "CustomFwHelper";
    public static final int REQUEST_PICK_FW = 0x4F1A;
    public static final String CUSTOM_FW_NAME = "custom.ufw";
    private static final int VER_BTN_ID = 0x4F1D;

    /** VersionListActivity: 200x50dp button below 开始升级 starting the flow. */
    public static void addVersionEntryButton(final Activity act) {
        try {
            View start = findById(act, "btnStart");
            if (start == null) {
                return;
            }
            ViewGroup root = (ViewGroup) act.findViewById(android.R.id.content);
            if (root == null || root.findViewWithTag("hlk_ver") != null) {
                return; // already added
            }
            Button b = new Button(act);
            b.setTag("hlk_ver");
            b.setId(VER_BTN_ID);
            b.setText("自定义固件升级");
            b.setAllCaps(false);
            styleFrom(b, start);
            b.setOnClickListener(new View.OnClickListener() {
                @Override
                public void onClick(View v) {
                    pickFirmware(act);
                }
            });
            android.widget.FrameLayout.LayoutParams flp = new android.widget.FrameLayout.LayoutParams(
                    dp(act, 200), dp(act, 50), Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
            flp.setMargins(0, 0, 0, dp(act, 115));
            root.addView(b, flp);
        } catch (Throwable t) {
            Log.e(TAG, "addVersionEntryButton failed", t);
        }
    }

    public static void pickFirmware(Activity activity) {
        try {
            Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
            intent.addCategory(Intent.CATEGORY_OPENABLE);
            intent.setType("*/*");
            intent.putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"application/octet-stream"});
            activity.startActivityForResult(intent, REQUEST_PICK_FW);
        } catch (Throwable t) {
            Log.e(TAG, "pickFirmware failed", t);
        }
    }

    /**
     * Validates the picked .ufw/.bfu file, copies it into the firmware cache,
     * fakes VersionListActivity.selectVersion and launches NewOTAInfoActivityV2.
     * Returns true when the OTA page was launched.
     */
    public static boolean handleVersionPick(Activity act, Intent data) {
        try {
            Uri uri = data.getData();
            if (uri == null) {
                return false;
            }
            String picked = queryDisplayName(act, uri);
            if (picked == null
                    || !(picked.toLowerCase().endsWith(".ufw") || picked.toLowerCase().endsWith(".bfu"))) {
                toast(act, "请选择 .ufw 固件文件");
                return false;
            }
            String cacheDir = getAppCacheDir();
            if (cacheDir == null) {
                return false;
            }
            String dst = cacheDir + "/" + CUSTOM_FW_NAME;
            long n = copyTo(act, uri, dst);
            if (n <= 0) {
                toast(act, "固件文件读取失败");
                return false;
            }
            Class<?> bean = Class.forName("com.hlk.hlkradartool.http.FirmwareInfoBean");
            Object sv = bean.newInstance();
            bean.getField("name").set(sv, CUSTOM_FW_NAME);
            bean.getField("fileSize").setInt(sv, (int) n);
            bean.getField("filePath").set(sv, "");
            bean.getField("sVersions").set(sv, "custom");
            Class<?> vla = Class.forName("com.hlk.hlkradartool.activity.VersionListActivity");
            Object inst = vla.getMethod("getInstance").invoke(null);
            vla.getField("selectVersion").set(inst, sv);

            Intent i = new Intent(act, Class.forName("com.hlk.hlkradartool.activity.NewOTAInfoActivityV2"));
            i.putExtra("address", macOf());
            i.putExtra("verInfo", verOf());
            i.putExtra("firmwareCode", 2);
            act.startActivity(i);
            return true;
        } catch (Throwable t) {
            Log.e(TAG, "handleVersionPick failed", t);
            return false;
        }
    }

    /** Copies the picked document to dstPath; returns bytes copied or -1. */
    public static long copyTo(Context context, Uri uri, String dstPath) {
        InputStream in = null;
        OutputStream out = null;
        long total = 0L;
        try {
            in = context.getContentResolver().openInputStream(uri);
            if (in == null) {
                return -1L;
            }
            out = new FileOutputStream(dstPath);
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
                total += n;
            }
        } catch (Throwable t) {
            return -1L;
        } finally {
            if (in != null) {
                try { in.close(); } catch (Exception e) { }
            }
            if (out != null) {
                try { out.close(); } catch (Exception e) { }
            }
        }
        return total;
    }

    private static String queryDisplayName(Context context, Uri uri) {
        Cursor c = null;
        try {
            c = context.getContentResolver().query(uri, null, null, null, null);
            if (c != null && c.moveToFirst()) {
                int idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (idx >= 0) {
                    return c.getString(idx);
                }
            }
        } catch (Throwable t) {
            // fall through
        } finally {
            if (c != null) {
                try { c.close(); } catch (Exception e) { }
            }
        }
        return null;
    }

    private static String getAppCacheDir() {
        try {
            Class<?> appCls = Class.forName("com.hlk.hlkradartool.activity.DemoApplication");
            return (String) appCls.getMethod("getAppCacheDirPath")
                    .invoke(appCls.getMethod("getInstance").invoke(null));
        } catch (Throwable t) {
            return null;
        }
    }

    private static String macOf() {
        try {
            Class<?> appCls = Class.forName("com.hlk.hlkradartool.activity.DemoApplication");
            Object app = appCls.getMethod("getInstance").invoke(null);
            Object sel = appCls.getField("nowSelectDevice").get(app);
            return (String) sel.getClass().getMethod("getMACAddress").invoke(sel);
        } catch (Throwable t) {
            return null;
        }
    }

    private static String verOf() {
        try {
            Class<?> appCls = Class.forName("com.hlk.hlkradartool.activity.DemoApplication");
            Object app = appCls.getMethod("getInstance").invoke(null);
            Object sel = appCls.getField("nowSelectDevice").get(app);
            return (String) sel.getClass().getMethod("getStrVerInfo").invoke(sel);
        } catch (Throwable t) {
            return "";
        }
    }

    private static void toast(Context c, String msg) {
        try {
            Toast.makeText(c, msg, Toast.LENGTH_SHORT).show();
        } catch (Throwable t) {
            // ignore
        }
    }

    private static void styleFrom(Button target, View ref) {
        if (ref instanceof TextView) {
            TextView r = (TextView) ref;
            target.setTextSize(TypedValue.COMPLEX_UNIT_PX, r.getTextSize());
            target.setTextColor(r.getTextColors());
            target.setTypeface(r.getTypeface());
        }
        Drawable bg = ref.getBackground();
        if (bg != null && bg.getConstantState() != null) {
            target.setBackgroundDrawable(bg.getConstantState().newDrawable());
        }
    }

    private static View findById(Activity a, String name) {
        int id = a.getResources().getIdentifier(name, "id", a.getPackageName());
        return id == 0 ? null : a.findViewById(id);
    }

    private static int dp(Activity act, int v) {
        return (int) (v * act.getResources().getDisplayMetrics().density);
    }
}
