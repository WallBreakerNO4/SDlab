"use client";

import { useTranslations } from "next-intl";
import { useCallback, useState } from "react";
import { useAuth } from "./auth-provider";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

type AuthLoginDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function AuthLoginDialog({ open, onOpenChange }: AuthLoginDialogProps) {
  const t = useTranslations("auth");
  const { signInWithGitHub, signInWithGoogle, signInWithMicrosoft } = useAuth();
  const [signingIn, setSigningIn] = useState<
    "github" | "google" | "microsoft" | null
  >(null);

  const handleGitHub = useCallback(async () => {
    setSigningIn("github");
    try {
      await signInWithGitHub();
    } finally {
      setSigningIn(null);
    }
  }, [signInWithGitHub]);

  const handleMicrosoft = useCallback(async () => {
    setSigningIn("microsoft");
    try {
      await signInWithMicrosoft();
    } finally {
      setSigningIn(null);
    }
  }, [signInWithMicrosoft]);

  const handleGoogle = useCallback(async () => {
    setSigningIn("google");
    try {
      await signInWithGoogle();
    } finally {
      setSigningIn(null);
    }
  }, [signInWithGoogle]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("title")}</DialogTitle>
          <DialogDescription>{t("description")}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 pt-2">
          <Button
            type="button"
            variant="outline"
            className="w-full gap-2"
            disabled={signingIn !== null}
            onClick={() => void handleGitHub()}
          >
            <svg
              className="size-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
            {signingIn === "github" ? t("redirecting") : t("github")}
          </Button>

          <Button
            type="button"
            variant="outline"
            className="w-full gap-2"
            disabled={signingIn !== null}
            onClick={() => void handleGoogle()}
          >
            <svg
              className="size-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            {signingIn === "google" ? t("redirecting") : t("google")}
          </Button>

          <Button
            type="button"
            variant="outline"
            className="w-full gap-2"
            disabled={signingIn !== null}
            onClick={() => void handleMicrosoft()}
          >
            <svg
              className="size-4"
              viewBox="0 0 24 24"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M11.4 24H0V12.6h11.4V24zM24 24H12.6V12.6H24V24zM11.4 11.4H0V0h11.4v11.4zM24 11.4H12.6V0H24v11.4z" />
            </svg>
            {signingIn === "microsoft" ? t("redirecting") : t("microsoft")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
