package com.faheem.education;

import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.ViewGroup;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.core.view.ViewCompat;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

public final class MainActivity extends ComponentActivity {
    private static final int FILE_PICKER_REQUEST = 4102;

    private WebView webView;
    private LinearLayout loadingPanel;
    private LinearLayout errorPanel;
    private ProgressBar loadingProgress;
    private Uri serverUri;
    private ValueCallback<Uri[]> fileChooserCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        configureSystemBars();
        configureWindowInsets();

        Uri configuredUri = Uri.parse(BuildConfig.FAHEEM_SERVER_URL);
        if (!"https".equalsIgnoreCase(configuredUri.getScheme())
                || configuredUri.getHost() == null) {
            throw new IllegalStateException("The configured Faheem server must use HTTPS.");
        }
        serverUri = configuredUri;

        webView = findViewById(R.id.web_view);
        loadingPanel = findViewById(R.id.loading_panel);
        errorPanel = findViewById(R.id.error_panel);
        loadingProgress = findViewById(R.id.loading_progress);
        Button retryButton = findViewById(R.id.retry_button);
        retryButton.setOnClickListener(view -> loadFaheem());

        configureWebView();
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                handleApplicationBack();
            }
        });

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            loadFaheem();
        }
    }

    private void configureSystemBars() {
        Window window = getWindow();
        WindowCompat.setDecorFitsSystemWindows(window, false);
        window.setStatusBarColor(Color.TRANSPARENT);
        window.setNavigationBarColor(Color.TRANSPARENT);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            window.setNavigationBarContrastEnforced(false);
        }
        WindowInsetsControllerCompat controller =
                WindowCompat.getInsetsController(window, window.getDecorView());
        controller.setAppearanceLightStatusBars(true);
        controller.setAppearanceLightNavigationBars(true);
        window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
    }

    private void configureWindowInsets() {
        View root = findViewById(R.id.app_root);
        ViewCompat.setOnApplyWindowInsetsListener(root, (view, windowInsets) -> {
            androidx.core.graphics.Insets bars =
                    windowInsets.getInsets(WindowInsetsCompat.Type.systemBars());
            androidx.core.graphics.Insets ime =
                    windowInsets.getInsets(WindowInsetsCompat.Type.ime());
            view.setPadding(
                    bars.left,
                    bars.top,
                    bars.right,
                    Math.max(bars.bottom, ime.bottom)
            );
            return windowInsets;
        });
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            settings.setSafeBrowsingEnabled(true);
        }

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            cookies.setAcceptThirdPartyCookies(webView, false);
        }

        webView.setOverScrollMode(View.OVER_SCROLL_NEVER);
        webView.setWebViewClient(new FaheemWebViewClient());
        webView.setWebChromeClient(new FaheemWebChromeClient());
        webView.addJavascriptInterface(new ThemeBridge(), "FaheemAndroid");
    }

    private void handleApplicationBack() {
        if (webView == null || webView.getVisibility() != View.VISIBLE) {
            goBackOrFinish();
            return;
        }
        webView.evaluateJavascript(
                "(function(){"
                        + "const overlay=document.querySelector("
                        + "'.settings-overlay:not(.hidden),.auth-overlay:not(.hidden)');"
                        + "const sidebar=document.querySelector('.sidebar.mobile-open');"
                        + "if(!overlay&&!sidebar)return false;"
                        + "document.dispatchEvent(new KeyboardEvent('keydown',"
                        + "{key:'Escape',bubbles:true}));return true;"
                        + "})()",
                handled -> {
                    if (!"true".equals(handled)) {
                        goBackOrFinish();
                    }
                }
        );
    }

    private void applySystemTheme(String theme) {
        boolean dark = "dark".equals(theme);
        int color = Color.parseColor(dark ? "#101114" : "#ffffff");
        runOnUiThread(() -> {
            Window window = getWindow();
            window.setStatusBarColor(color);
            window.setNavigationBarColor(color);
            WindowInsetsControllerCompat controller =
                    WindowCompat.getInsetsController(window, window.getDecorView());
            controller.setAppearanceLightStatusBars(!dark);
            controller.setAppearanceLightNavigationBars(!dark);
        });
    }

    private final class ThemeBridge {
        @JavascriptInterface
        public void setTheme(String theme) {
            if ("light".equals(theme) || "dark".equals(theme)) {
                applySystemTheme(theme);
            }
        }
    }

    private void loadFaheem() {
        if (webView == null) {
            createWebView();
        }
        errorPanel.setVisibility(View.GONE);
        loadingPanel.setVisibility(View.VISIBLE);
        loadingProgress.setVisibility(View.VISIBLE);
        webView.setVisibility(View.VISIBLE);
        webView.loadUrl(serverUri.toString());
    }

    private void showConnectionError() {
        loadingPanel.setVisibility(View.GONE);
        loadingProgress.setVisibility(View.GONE);
        errorPanel.setVisibility(View.VISIBLE);
    }

    private void goBackOrFinish() {
        if (webView != null
                && errorPanel.getVisibility() == View.VISIBLE
                && webView.canGoBack()) {
            errorPanel.setVisibility(View.GONE);
            webView.goBack();
        } else if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            finish();
        }
    }

    private void createWebView() {
        webView = new WebView(this);
        webView.setId(R.id.web_view);
        FrameLayout.LayoutParams layoutParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
        );
        FrameLayout root = findViewById(R.id.app_root);
        root.addView(webView, 0, layoutParams);
        configureWebView();
    }

    private void discardCrashedWebView(WebView crashedView) {
        ViewGroup parent = (ViewGroup) crashedView.getParent();
        if (parent != null) {
            parent.removeView(crashedView);
        }
        crashedView.setWebChromeClient(null);
        crashedView.setWebViewClient(null);
        crashedView.destroy();
        if (webView == crashedView) {
            webView = null;
        }
        if (fileChooserCallback != null) {
            fileChooserCallback.onReceiveValue(null);
            fileChooserCallback = null;
        }
    }

    private boolean handleNavigation(String target) {
        Uri uri = Uri.parse(target);
        String scheme = uri.getScheme() == null
                ? ""
                : uri.getScheme().toLowerCase(Locale.ROOT);
        if ("https".equals(scheme) && sameServerOrigin(uri)) {
            return false;
        }
        if (!"https".equals(scheme) && !"mailto".equals(scheme) && !"tel".equals(scheme)) {
            return true;
        }
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri));
        } catch (ActivityNotFoundException error) {
            Toast.makeText(this, R.string.connection_error_message, Toast.LENGTH_SHORT).show();
        }
        return true;
    }

    private boolean sameServerOrigin(Uri candidate) {
        if (candidate.getHost() == null
                || !candidate.getHost().equalsIgnoreCase(serverUri.getHost())) {
            return false;
        }
        int expectedPort = serverUri.getPort() == -1 ? 443 : serverUri.getPort();
        int actualPort = candidate.getPort() == -1 ? 443 : candidate.getPort();
        return expectedPort == actualPort && candidate.getUserInfo() == null;
    }

    private boolean openFilePicker(WebChromeClient.FileChooserParams params) {
        if (params == null || fileChooserCallback == null) {
            return false;
        }

        Set<String> mimeTypes = new LinkedHashSet<>();
        for (String acceptedType : params.getAcceptTypes()) {
            if (acceptedType == null) {
                continue;
            }
            for (String value : acceptedType.split(",")) {
                String mimeType = value.trim();
                if (mimeType.matches("[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+*-]+")) {
                    mimeTypes.add(mimeType);
                }
            }
        }

        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        picker.addCategory(Intent.CATEGORY_OPENABLE);
        picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false);
        if (mimeTypes.size() == 1) {
            picker.setType(mimeTypes.iterator().next());
        } else {
            picker.setType("*/*");
            if (!mimeTypes.isEmpty()) {
                picker.putExtra(Intent.EXTRA_MIME_TYPES, mimeTypes.toArray(new String[0]));
            }
        }

        try {
            startActivityForResult(picker, FILE_PICKER_REQUEST);
            return true;
        } catch (ActivityNotFoundException error) {
            fileChooserCallback.onReceiveValue(null);
            fileChooserCallback = null;
            Toast.makeText(this, R.string.connection_error_message, Toast.LENGTH_SHORT).show();
            return true;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != FILE_PICKER_REQUEST || fileChooserCallback == null) {
            return;
        }
        Uri[] result = resultCode == RESULT_OK && data != null && data.getData() != null
                ? new Uri[]{data.getData()}
                : null;
        fileChooserCallback.onReceiveValue(result);
        fileChooserCallback = null;
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        if (webView != null) {
            webView.saveState(outState);
        }
        super.onSaveInstanceState(outState);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.onPause();
        }
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        if (fileChooserCallback != null) {
            fileChooserCallback.onReceiveValue(null);
            fileChooserCallback = null;
        }
        if (webView != null) {
            webView.stopLoading();
            webView.setWebChromeClient(null);
            webView.setWebViewClient(null);
            ViewGroup parent = (ViewGroup) webView.getParent();
            if (parent != null) {
                parent.removeView(webView);
            }
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }

    private final class FaheemWebViewClient extends WebViewClient {
        private boolean mainFrameFailed;

        @Override
        public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
            mainFrameFailed = false;
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            return handleNavigation(request.getUrl().toString());
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, String url) {
            return handleNavigation(url);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (mainFrameFailed) {
                showConnectionError();
                return;
            }
            loadingPanel.setVisibility(View.GONE);
            loadingProgress.setVisibility(View.GONE);
            errorPanel.setVisibility(View.GONE);
            CookieManager.getInstance().flush();
            if (sameServerOrigin(Uri.parse(url))) {
                view.evaluateJavascript(
                        "(function(){"
                                + "const sync=()=>window.FaheemAndroid.setTheme("
                                + "document.documentElement.dataset.theme||'light');"
                                + "sync();new MutationObserver(sync).observe("
                                + "document.documentElement,{attributes:true,"
                                + "attributeFilter:['data-theme']});"
                                + "})()",
                        null
                );
            }
        }

        @Override
        public void onReceivedError(
                WebView view,
                WebResourceRequest request,
                WebResourceError error
        ) {
            if (request.isForMainFrame()) {
                mainFrameFailed = true;
                showConnectionError();
            }
        }

        @Override
        public void onReceivedHttpError(
                WebView view,
                WebResourceRequest request,
                android.webkit.WebResourceResponse response
        ) {
            if (request.isForMainFrame() && response.getStatusCode() >= 500) {
                mainFrameFailed = true;
                showConnectionError();
            }
        }

        @Override
        public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            mainFrameFailed = true;
            discardCrashedWebView(view);
            showConnectionError();
            return true;
        }
    }

    private final class FaheemWebChromeClient extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(
                WebView view,
                ValueCallback<Uri[]> filePathCallback,
                FileChooserParams fileChooserParams
        ) {
            if (fileChooserCallback != null) {
                fileChooserCallback.onReceiveValue(null);
            }
            fileChooserCallback = filePathCallback;
            return openFilePicker(fileChooserParams);
        }

        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            loadingProgress.setVisibility(newProgress < 100 ? View.VISIBLE : View.GONE);
        }
    }
}
