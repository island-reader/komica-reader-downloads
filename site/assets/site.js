"use strict";

const ALLOWED_FILE_NAMES = Object.freeze({
  windows: "komica-terminal-reader-windows.zip",
  posix: "komica-terminal-reader-posix.tar.gz",
  checksums: "SHA256SUMS.txt",
});

function safeReleaseUrl(baseUrl, fileName) {
  const base = new URL(baseUrl, window.location.href);
  const resolved = new URL(fileName, base.href.endsWith("/") ? base : `${base.href}/`);
  if (resolved.protocol !== "https:" && resolved.origin !== window.location.origin) {
    throw new Error("下載網址必須使用 HTTPS 或同網域相對路徑。");
  }
  return resolved.href;
}

function enableLink(element, url) {
  element.href = url;
  element.removeAttribute("aria-disabled");
}

function showUnavailable(message) {
  document.querySelector("#release-version").textContent = "尚未開放";
  document.querySelector("#release-status").textContent = message;
}

async function loadRelease() {
  try {
    const response = await fetch("release.json", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) {
      throw new Error(`release.json 回應 ${response.status}`);
    }

    const release = await response.json();
    if (!/^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$/.test(release.version)) {
      throw new Error("版本格式不正確。");
    }
    if (typeof release.base_url !== "string" || release.base_url.length === 0) {
      throw new Error("尚未設定下載來源。");
    }

    document.querySelector("#release-version").textContent = release.version;
    if (release.published_at) {
      const published = new Date(release.published_at);
      if (!Number.isNaN(published.valueOf())) {
        document.querySelector("#release-date").textContent =
          `發行日期：${new Intl.DateTimeFormat("zh-TW", { dateStyle: "long" }).format(published)}`;
      }
    }

    for (const platform of ["windows", "posix"]) {
      const link = document.querySelector(`[data-download="${platform}"]`);
      enableLink(link, safeReleaseUrl(release.base_url, ALLOWED_FILE_NAMES[platform]));
    }
    enableLink(
      document.querySelector("#checksum-link"),
      safeReleaseUrl(release.base_url, ALLOWED_FILE_NAMES.checksums),
    );
    document.querySelector("#release-status").textContent =
      "已載入檔案檢查碼；下載後可以 SHA-256 核對檔案。";
  } catch (error) {
    showUnavailable("下載區尚未完成設定，請稍後再試。");
  }
}

loadRelease();
