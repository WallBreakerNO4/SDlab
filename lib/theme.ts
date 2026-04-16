export const THEME_STORAGE_KEY = "theme";
export const THEME_COOKIE_NAME = "theme";
export const THEME_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export type ThemePreference = "light" | "dark";

export function parseThemePreference(
  value: string | null | undefined,
): ThemePreference | null {
  if (value === "light" || value === "dark") {
    return value;
  }

  return null;
}

export function getThemeBootstrapScript(): string {
  return `
    (function () {
      try {
        var storageKey = ${JSON.stringify(THEME_STORAGE_KEY)};
        var cookieName = ${JSON.stringify(THEME_COOKIE_NAME)};
        var theme = localStorage.getItem(storageKey);

        if (theme !== "light" && theme !== "dark") {
          var cookieEntry = document.cookie
            .split("; ")
            .find(function (entry) {
              return entry.indexOf(cookieName + "=") === 0;
            });

          if (cookieEntry) {
            theme = decodeURIComponent(cookieEntry.slice(cookieName.length + 1));
          }
        }

        if (theme !== "light" && theme !== "dark") {
          theme = window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
        }

        var root = document.documentElement;
        root.classList.remove("light", "dark");
        root.classList.add(theme);
        root.style.colorScheme = theme;
      } catch (_error) {}
    })();
  `;
}
