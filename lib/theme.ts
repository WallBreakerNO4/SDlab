export const THEME_STORAGE_KEY = "theme";
export const THEME_COOKIE_NAME = "theme";
export const THEME_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;
export const LIGHT_THEME_BACKGROUND = "oklch(0.985 0.002 260)";
export const LIGHT_THEME_FOREGROUND = "oklch(0.145 0.005 260)";
export const DARK_THEME_BACKGROUND = "oklch(0.13 0.01 260)";
export const DARK_THEME_FOREGROUND = "oklch(0.985 0.005 260)";

export type ThemePreference = "light" | "dark";

export function parseThemePreference(
  value: string | null | undefined,
): ThemePreference | null {
  if (value === "light" || value === "dark") {
    return value;
  }

  return null;
}

function getThemeColors(theme: ThemePreference) {
  if (theme === "dark") {
    return {
      backgroundColor: DARK_THEME_BACKGROUND,
      color: DARK_THEME_FOREGROUND,
    };
  }

  return {
    backgroundColor: LIGHT_THEME_BACKGROUND,
    color: LIGHT_THEME_FOREGROUND,
  };
}

export function getThemeInlineStyle(theme: ThemePreference) {
  return {
    ...getThemeColors(theme),
    colorScheme: theme,
  };
}

export function getThemeCriticalCss(): string {
  return `
    html, body {
      background-color: ${LIGHT_THEME_BACKGROUND};
      color: ${LIGHT_THEME_FOREGROUND};
    }

    @media (prefers-color-scheme: dark) {
      html, body {
        background-color: ${DARK_THEME_BACKGROUND};
        color: ${DARK_THEME_FOREGROUND};
      }
    }

    html.light,
    html.light body {
      background-color: ${LIGHT_THEME_BACKGROUND};
      color: ${LIGHT_THEME_FOREGROUND};
      color-scheme: light;
    }

    html.dark,
    html.dark body {
      background-color: ${DARK_THEME_BACKGROUND};
      color: ${DARK_THEME_FOREGROUND};
      color-scheme: dark;
    }
  `;
}

export function getThemeBootstrapScript(): string {
  return `
    (function () {
      try {
        var cookieName = ${JSON.stringify(THEME_COOKIE_NAME)};
        var lightBackground = ${JSON.stringify(LIGHT_THEME_BACKGROUND)};
        var lightForeground = ${JSON.stringify(LIGHT_THEME_FOREGROUND)};
        var darkBackground = ${JSON.stringify(DARK_THEME_BACKGROUND)};
        var darkForeground = ${JSON.stringify(DARK_THEME_FOREGROUND)};
        var theme = null;
        var cookieEntry = document.cookie
          .split("; ")
          .find(function (entry) {
            return entry.indexOf(cookieName + "=") === 0;
          });

        if (cookieEntry) {
          theme = decodeURIComponent(cookieEntry.slice(cookieName.length + 1));
        }

        if (theme !== "light" && theme !== "dark") {
          theme = window.matchMedia("(prefers-color-scheme: dark)").matches
            ? "dark"
            : "light";
        }

        var root = document.documentElement;
        var background = theme === "dark" ? darkBackground : lightBackground;
        var foreground = theme === "dark" ? darkForeground : lightForeground;
        root.classList.remove("light", "dark");
        root.classList.add(theme);
        root.style.colorScheme = theme;
        root.style.backgroundColor = background;
        root.style.color = foreground;

        var applyBodyTheme = function () {
          if (!document.body) {
            return;
          }

          document.body.style.backgroundColor = background;
          document.body.style.color = foreground;
        };

        applyBodyTheme();
        document.addEventListener("DOMContentLoaded", applyBodyTheme, {
          once: true,
        });
      } catch (_error) {}
    })();
  `;
}
