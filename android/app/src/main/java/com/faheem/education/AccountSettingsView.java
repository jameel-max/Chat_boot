package com.faheem.education;

import android.content.Context;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.method.HideReturnsTransformationMethod;
import android.text.method.PasswordTransformationMethod;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.TextView;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

final class AccountSettingsView extends LinearLayout {
    interface ThemeListener {
        void onThemeChanged(String theme);
    }

    interface Action {
        void run();
    }

    private interface RequestCallback {
        void onComplete(JSONObject response, Exception error);
    }

    private static final int TEAL = Color.rgb(14, 143, 120);
    private static final int LIGHT_BACKGROUND = Color.rgb(244, 248, 250);
    private static final int DARK_BACKGROUND = Color.rgb(16, 17, 20);
    private static final int LIGHT_TEXT = Color.rgb(19, 32, 51);
    private static final int DARK_TEXT = Color.rgb(237, 240, 244);
    private static final int LIGHT_MUTED = Color.rgb(90, 107, 130);
    private static final int DARK_MUTED = Color.rgb(173, 181, 194);

    private final Uri serverUri;
    private final CookieManager cookieManager;
    private final ThemeListener themeListener;
    private final Action logoutAction;
    private final Action closeAction;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final List<View> cards = new ArrayList<>();
    private final List<TextView> themedText = new ArrayList<>();

    private LinearLayout content;
    private LinearLayout header;
    private TextView message;
    private EditText nameInput;
    private EditText phoneInput;
    private Spinner gradeInput;
    private EditText currentPasswordInput;
    private EditText newPasswordInput;
    private EditText confirmPasswordInput;
    private Button lightThemeButton;
    private Button darkThemeButton;
    private String currentTheme = "light";
    private boolean released;

    AccountSettingsView(
            Context context,
            Uri serverUri,
            CookieManager cookieManager,
            ThemeListener themeListener,
            Action logoutAction,
            Action closeAction
    ) {
        super(context);
        this.serverUri = serverUri;
        this.cookieManager = cookieManager;
        this.themeListener = themeListener;
        this.logoutAction = logoutAction;
        this.closeAction = closeAction;
        setOrientation(VERTICAL);
        setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        buildView();
        applyThemeColors();
    }

    void loadAccount() {
        message.setText("جارٍ تحميل إعدادات الحساب...");
        request("/api/me", "GET", null, (account, accountError) -> {
            if (accountError != null) {
                showError(accountError.getMessage());
                return;
            }
            JSONObject user = account.optJSONObject("user");
            if (user == null) {
                showError("تعذّر تحميل بيانات الحساب.");
                return;
            }
            boolean isStudent = user.optBoolean("isStudentAccount", false);
            findViewWithTag("student-account").setVisibility(
                    isStudent ? View.VISIBLE : View.GONE
            );
            if (isStudent) {
                request("/api/account/profile", "GET", null, (profileResult, profileError) -> {
                    if (profileError != null) {
                        showError(profileError.getMessage());
                        return;
                    }
                    JSONObject profile = profileResult.optJSONObject("profile");
                    if (profile != null) {
                        nameInput.setText(profile.optString("fullName", ""));
                        phoneInput.setText(profile.optString("phone", ""));
                        selectGrade(profile.optString("grade", ""));
                    }
                    loadPreferences();
                });
            } else {
                loadPreferences();
            }
        });
    }

    void release() {
        released = true;
        executor.shutdownNow();
    }

    private void buildView() {
        header = new LinearLayout(getContext());
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setPadding(dp(18), dp(10), dp(18), dp(12));
        header.setBackgroundColor(Color.WHITE);
        addView(header, new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        Button back = new Button(getContext());
        back.setText("رجوع");
        back.setTextColor(TEAL);
        back.setOnClickListener(view -> closeAction.run());
        header.addView(back, new LayoutParams(dp(84), dp(48)));

        TextView title = text("الإعدادات", 22, true);
        LayoutParams titleParams = new LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1);
        titleParams.setMarginStart(dp(12));
        header.addView(title, titleParams);

        ScrollView scroll = new ScrollView(getContext());
        scroll.setFillViewport(true);
        addView(scroll, new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                0,
                1
        ));
        content = new LinearLayout(getContext());
        content.setOrientation(VERTICAL);
        content.setPadding(dp(16), dp(16), dp(16), dp(24));
        scroll.addView(content, new ScrollView.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));

        message = text("", 14, false);
        message.setPadding(dp(4), dp(4), dp(4), dp(8));
        content.addView(message);

        LinearLayout studentCard = card("student-account");
        addHeading(studentCard, "اسم المستخدم", "أدخل اسمك العربي الرباعي كما في الموقع.");
        nameInput = field("الاسم، اسم الأب، اسم الجد، العائلة", InputType.TYPE_CLASS_TEXT);
        studentCard.addView(nameInput, fieldParams());
        addActionButton(studentCard, "حفظ الاسم", view -> saveName());

        addHeading(studentCard, "رقم الهاتف", "حدّث رقم هاتفك الأردني المرتبط بحسابك.");
        phoneInput = field("079 123 4567 أو +962 79 123 4567",
                InputType.TYPE_CLASS_PHONE);
        phoneInput.setTextDirection(View.TEXT_DIRECTION_LTR);
        studentCard.addView(phoneInput, fieldParams());
        addActionButton(studentCard, "حفظ رقم الهاتف", view -> savePhone());

        addHeading(studentCard, "الصف الدراسي", "اختر صفك الحالي لتناسب الإجابات منهجك.");
        gradeInput = new Spinner(getContext());
        gradeInput.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        String[] gradeLabels = {
                "اختر صفك",
                "الصف الثامن",
                "الصف التاسع",
                "الصف العاشر",
                "الأول الثانوي",
                "الثاني الثانوي"
        };
        ArrayAdapter<String> gradeAdapter = new ArrayAdapter<>(
                getContext(),
                android.R.layout.simple_spinner_item,
                gradeLabels
        );
        gradeAdapter.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item);
        gradeInput.setAdapter(gradeAdapter);
        studentCard.addView(gradeInput, fieldParams());
        addActionButton(studentCard, "حفظ الصف", view -> saveGrade());

        LinearLayout appearanceCard = card(null);
        addHeading(appearanceCard, "المظهر", "اختر المظهر الذي تفضله.");
        LinearLayout themeRow = new LinearLayout(getContext());
        themeRow.setOrientation(HORIZONTAL);
        lightThemeButton = themeButton("☀  فاتح", "light");
        darkThemeButton = themeButton("☾  داكن", "dark");
        themeRow.addView(lightThemeButton, new LayoutParams(0, dp(48), 1));
        LayoutParams darkParams = new LayoutParams(0, dp(48), 1);
        darkParams.setMarginStart(dp(10));
        themeRow.addView(darkThemeButton, darkParams);
        appearanceCard.addView(themeRow);

        LinearLayout passwordCard = card(null);
        addHeading(passwordCard, "تغيير كلمة المرور", "كلمة المرور الجديدة يجب ألا تقل عن 10 أحرف.");
        currentPasswordInput = passwordField(passwordCard, "كلمة المرور الحالية");
        newPasswordInput = passwordField(passwordCard, "كلمة المرور الجديدة");
        confirmPasswordInput = passwordField(passwordCard, "تأكيد كلمة المرور الجديدة");
        addActionButton(passwordCard, "حفظ كلمة المرور", view -> changePassword());

        LinearLayout logoutCard = card(null);
        addHeading(logoutCard, "تسجيل الخروج", "إنهاء جلسة الحساب على هذا الجهاز.");
        Button logout = new Button(getContext());
        logout.setText("تسجيل الخروج");
        logout.setTextColor(Color.WHITE);
        logout.setBackgroundTintList(android.content.res.ColorStateList.valueOf(
                Color.rgb(176, 55, 55)
        ));
        logout.setOnClickListener(view -> logout());
        logoutCard.addView(logout, new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(48)
        ));
    }

    private LinearLayout card(String tag) {
        LinearLayout card = new LinearLayout(getContext());
        card.setOrientation(VERTICAL);
        card.setPadding(dp(16), dp(16), dp(16), dp(16));
        card.setBackground(roundRect(Color.WHITE, dp(18)));
        LayoutParams params = new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.bottomMargin = dp(14);
        content.addView(card, params);
        cards.add(card);
        if (tag != null) {
            card.setTag(tag);
        }
        return card;
    }

    private void addHeading(LinearLayout parent, String heading, String description) {
        TextView title = text(heading, 18, true);
        parent.addView(title, new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        TextView detail = text(description, 13, false);
        LayoutParams detailParams = new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        detailParams.topMargin = dp(4);
        detailParams.bottomMargin = dp(12);
        parent.addView(detail, detailParams);
    }

    private EditText field(String hint, int inputType) {
        EditText editText = new EditText(getContext());
        editText.setSingleLine(true);
        editText.setTextSize(15);
        editText.setHint(hint);
        editText.setInputType(inputType);
        editText.setPadding(dp(12), dp(8), dp(12), dp(8));
        editText.setBackground(roundRect(Color.rgb(245, 247, 249), dp(10)));
        editText.setTextColor(LIGHT_TEXT);
        editText.setHintTextColor(LIGHT_MUTED);
        editText.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        return editText;
    }

    private EditText passwordField(LinearLayout parent, String hint) {
        TextView label = text(hint, 14, true);
        LayoutParams labelParams = new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT
        );
        labelParams.topMargin = dp(8);
        parent.addView(label, labelParams);

        LinearLayout row = new LinearLayout(getContext());
        row.setOrientation(HORIZONTAL);
        LayoutParams rowParams = fieldParams();
        parent.addView(row, rowParams);

        EditText password = field(hint,
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setTextDirection(View.TEXT_DIRECTION_LTR);
        password.setTransformationMethod(PasswordTransformationMethod.getInstance());
        row.addView(password, new LayoutParams(0, dp(52), 1));
        Button toggle = new Button(getContext());
        toggle.setText("إظهار");
        toggle.setTextSize(12);
        toggle.setOnClickListener(view -> {
            boolean visible = password.getTransformationMethod()
                    instanceof PasswordTransformationMethod;
            password.setTransformationMethod(visible
                    ? HideReturnsTransformationMethod.getInstance()
                    : PasswordTransformationMethod.getInstance());
            toggle.setText(visible ? "إخفاء" : "إظهار");
            password.setSelection(password.length());
        });
        row.addView(toggle, new LayoutParams(dp(88), dp(52)));
        return password;
    }

    private Button themeButton(String label, String theme) {
        Button button = new Button(getContext());
        button.setText(label);
        button.setOnClickListener(view -> saveTheme(theme));
        return button;
    }

    private void addActionButton(LinearLayout parent, String label, OnClickListener listener) {
        Button button = new Button(getContext());
        button.setText(label);
        button.setTextColor(Color.WHITE);
        button.setBackgroundTintList(android.content.res.ColorStateList.valueOf(TEAL));
        button.setOnClickListener(listener);
        LayoutParams params = new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(48)
        );
        params.topMargin = dp(8);
        parent.addView(button, params);
    }

    private LayoutParams fieldParams() {
        LayoutParams params = new LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                dp(52)
        );
        params.bottomMargin = dp(10);
        return params;
    }

    private TextView text(String value, int size, boolean bold) {
        TextView textView = new TextView(getContext());
        textView.setText(value);
        textView.setTextSize(size);
        textView.setGravity(Gravity.CENTER_VERTICAL);
        if (bold) {
            textView.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        }
        themedText.add(textView);
        return textView;
    }

    private void loadPreferences() {
        request("/api/preferences", "GET", null, (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
                return;
            }
            JSONObject preferences = response.optJSONObject("preferences");
            currentTheme = preferences == null
                    ? "light"
                    : preferences.optString("theme", "light");
            if (!"dark".equals(currentTheme)) {
                currentTheme = "light";
            }
            applyThemeColors();
            themeListener.onThemeChanged(currentTheme);
            message.setText("");
        });
    }

    private void saveName() {
        String name = nameInput.getText().toString().trim();
        if (name.isEmpty()) {
            showError("أدخل الاسم الجديد.");
            return;
        }
        request("/api/account/name", "POST", json("fullName", name), (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
                return;
            }
            String savedName = response.optString("fullName", name);
            nameInput.setText(savedName);
            updateWebProfileName(savedName);
            showSuccess("تم تحديث اسم المستخدم بنجاح.");
        });
    }

    private void savePhone() {
        String phone = phoneInput.getText().toString().trim();
        if (phone.isEmpty()) {
            showError("أدخل رقم الهاتف الجديد.");
            return;
        }
        request("/api/account/phone", "POST", json("phone", phone), (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
                return;
            }
            phoneInput.setText(response.optString("phone", phone));
            showSuccess("تم تحديث رقم الهاتف بنجاح.");
        });
    }

    private void saveGrade() {
        int selection = gradeInput.getSelectedItemPosition();
        if (selection <= 0) {
            showError("اختر صفك الدراسي.");
            return;
        }
        String grade = String.valueOf(selection + 7);
        request("/api/account/grade", "POST", json("grade", grade), (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
                return;
            }
            updateWebProfileGrade(grade);
            showSuccess("تم تحديث صفك الدراسي بنجاح.");
        });
    }

    private void selectGrade(String grade) {
        try {
            int key = Integer.parseInt(grade);
            if (key >= 8 && key <= 12) {
                gradeInput.setSelection(key - 7);
            }
        } catch (NumberFormatException ignored) {
            gradeInput.setSelection(0);
        }
    }

    private void saveTheme(String theme) {
        request("/api/preferences", "POST", json("theme", theme), (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
                return;
            }
            currentTheme = theme;
            applyThemeColors();
            themeListener.onThemeChanged(theme);
            showSuccess("تم حفظ المظهر.");
        });
    }

    private void changePassword() {
        String current = currentPasswordInput.getText().toString();
        String next = newPasswordInput.getText().toString();
        String confirm = confirmPasswordInput.getText().toString();
        if (current.isEmpty() || next.isEmpty() || confirm.isEmpty()) {
            showError("أكمل حقول كلمة المرور.");
            return;
        }
        if (!next.equals(confirm)) {
            showError("كلمتا المرور الجديدتان غير متطابقتين.");
            return;
        }
        if (next.length() < 10) {
            showError("أنشئ كلمة مرور جديدة من 10 أحرف على الأقل.");
            return;
        }
        JSONObject payload = new JSONObject();
        try {
            payload.put("currentPassword", current);
            payload.put("newPassword", next);
            payload.put("confirmPassword", confirm);
        } catch (JSONException error) {
            showError("تعذّر تجهيز طلب تغيير كلمة المرور.");
            return;
        }
        request("/api/auth/change-password", "POST", payload, (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
                if (error.getMessage().contains("الحالية غير صحيحة")) {
                    currentPasswordInput.setText("");
                }
                return;
            }
            currentPasswordInput.setText("");
            newPasswordInput.setText("");
            confirmPasswordInput.setText("");
            showSuccess("تم تغيير كلمة المرور. أُنهيت الجلسات على الأجهزة الأخرى.");
        });
    }

    private void logout() {
        request("/api/logout", "POST", null, (response, error) -> {
            if (error != null) {
                showError(error.getMessage());
            } else {
                logoutAction.run();
            }
        });
    }

    private void updateWebProfileName(String name) {
        String escaped = JSONObject.quote(name);
        ((MainActivity) getContext()).runOnUiThread(() -> {
            MainActivity activity = (MainActivity) getContext();
            ((WebView) activity.findViewById(R.id.web_view)).evaluateJavascript(
                    "(function(){"
                            + "const name=" + escaped + ";"
                            + "const profile=document.querySelector('#profile-name');"
                            + "if(profile)profile.textContent=name;"
                            + "const input=document.querySelector('#username-input');"
                            + "if(input)input.value=name;"
                            + "const avatar=document.querySelector('#user-avatar-fallback');"
                            + "if(avatar)avatar.textContent=name.slice(0,1);"
                            + "})()",
                    null
            );
        });
    }

    private void updateWebProfileGrade(String grade) {
        String escaped = JSONObject.quote(grade);
        ((MainActivity) getContext()).runOnUiThread(() -> {
            MainActivity activity = (MainActivity) getContext();
            ((WebView) activity.findViewById(R.id.web_view)).evaluateJavascript(
                    "(function(){"
                            + "const grade=" + escaped + ";"
                            + "const input=document.querySelector('#grade-input');"
                            + "if(input)input.value=grade;"
                            + "})()",
                    null
            );
        });
    }

    private void request(String path, String method, JSONObject body, RequestCallback callback) {
        executor.execute(() -> {
            JSONObject response = null;
            Exception failure = null;
            try {
                response = performRequest(path, method, body);
            } catch (Exception error) {
                failure = error;
            }
            JSONObject result = response;
            Exception error = failure;
            mainHandler.post(() -> {
                if (!released) {
                    callback.onComplete(result, error);
                }
            });
        });
    }

    private JSONObject performRequest(String path, String method, JSONObject body)
            throws IOException {
        URL url = new URL(serverUri + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(20000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestMethod(method);
        connection.setRequestProperty("Accept", "application/json");
        String cookie = cookieManager.getCookie(serverUri.toString());
        if (cookie == null || cookie.isEmpty()) {
            throw new IOException("انتهت جلسة الدخول. سجّل الدخول مجددًا.");
        }
        connection.setRequestProperty("Cookie", cookie);
        if (body != null) {
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setDoOutput(true);
            try (java.io.OutputStream output = connection.getOutputStream()) {
                output.write(body.toString().getBytes(StandardCharsets.UTF_8));
            }
        }

        try {
            int status = connection.getResponseCode();
            for (Map.Entry<String, List<String>> header : connection.getHeaderFields().entrySet()) {
                if ("Set-Cookie".equalsIgnoreCase(header.getKey())) {
                    for (String value : header.getValue()) {
                        cookieManager.setCookie(serverUri.toString(), value);
                    }
                    cookieManager.flush();
                }
            }

            String responseText = "";
            if (status != HttpURLConnection.HTTP_NO_CONTENT) {
                InputStream stream = status >= 400
                        ? connection.getErrorStream()
                        : connection.getInputStream();
                responseText = stream == null ? "" : readFully(stream);
            }

            if (status < 200 || status >= 300) {
                String detail = "تعذّر إكمال الطلب.";
                try {
                    detail = new JSONObject(responseText).optString("error", detail);
                } catch (JSONException ignored) {
                    if (status == 401 || status == 403) {
                        detail = "انتهت جلسة الدخول أو لا تسمح الصلاحية بهذا الإجراء.";
                    }
                }
                throw new IOException(detail);
            }
            if (responseText.isEmpty()) {
                return new JSONObject();
            }
            try {
                return new JSONObject(responseText);
            } catch (JSONException error) {
                throw new IOException("أعاد الخادم استجابة غير صالحة.", error);
            }
        } finally {
            connection.disconnect();
        }
    }

    private static String readFully(InputStream stream) throws IOException {
        StringBuilder result = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(stream, StandardCharsets.UTF_8)
        )) {
            String line;
            while ((line = reader.readLine()) != null) {
                result.append(line);
            }
        }
        return result.toString();
    }

    private void showError(String text) {
        message.setText(text == null || text.isEmpty() ? "تعذّر إكمال الطلب." : text);
        message.setTextColor(Color.rgb(190, 48, 48));
    }

    private void showSuccess(String text) {
        message.setText(text);
        message.setTextColor(TEAL);
    }

    private void applyThemeColors() {
        boolean dark = "dark".equals(currentTheme);
        int background = dark ? DARK_BACKGROUND : LIGHT_BACKGROUND;
        int card = dark ? Color.rgb(31, 33, 38) : Color.WHITE;
        int text = dark ? DARK_TEXT : LIGHT_TEXT;
        int muted = dark ? DARK_MUTED : LIGHT_MUTED;
        setBackgroundColor(background);
        if (content != null) {
            content.setBackgroundColor(background);
        }
        if (header != null) {
            header.setBackgroundColor(card);
        }
        for (View cardView : cards) {
            cardView.setBackground(roundRect(card, dp(18)));
        }
        for (TextView textView : themedText) {
            textView.setTextColor(textView == message && message.getCurrentTextColor()
                    == Color.rgb(190, 48, 48)
                    ? Color.rgb(255, 120, 120)
                    : text);
        }
        if (nameInput != null) {
            int inputBackground = dark ? Color.rgb(43, 46, 52) : Color.rgb(245, 247, 249);
            if (gradeInput != null) {
                gradeInput.setBackground(roundRect(inputBackground, dp(10)));
            }
            for (EditText input : new EditText[]{
                    nameInput, phoneInput, currentPasswordInput,
                    newPasswordInput, confirmPasswordInput
            }) {
                if (input != null) {
                    input.setBackground(roundRect(inputBackground, dp(10)));
                    input.setTextColor(text);
                    input.setHintTextColor(muted);
                }
            }
        }
        if (lightThemeButton != null) {
            lightThemeButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(
                    "light".equals(currentTheme) ? TEAL : (dark ? 0xFF34373D : 0xFFE8EEF1)
            ));
            lightThemeButton.setTextColor("light".equals(currentTheme) ? Color.WHITE : text);
            darkThemeButton.setBackgroundTintList(android.content.res.ColorStateList.valueOf(
                    "dark".equals(currentTheme) ? TEAL : (dark ? 0xFF34373D : 0xFFE8EEF1)
            ));
            darkThemeButton.setTextColor("dark".equals(currentTheme) ? Color.WHITE : text);
        }
    }

    private static JSONObject json(String key, String value) {
        JSONObject object = new JSONObject();
        try {
            object.put(key, value);
        } catch (JSONException error) {
            throw new IllegalStateException(error);
        }
        return object;
    }

    private GradientDrawable roundRect(int color, int radius) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(color);
        drawable.setCornerRadius(radius);
        return drawable;
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
