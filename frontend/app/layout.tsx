import type { Metadata } from "next";
import { Figtree, JetBrains_Mono } from "next/font/google";
import { InlineScript } from "@/components/shared/InlineScript";
import "./globals.css";

// Figtree carries the interface — friendly and geometric without being childish.
// Deliberately not Inter or Space Grotesk: those two are on every AI product
// and were part of why the old build read as generated.
const figtree = Figtree({
  subsets: ["latin"],
  variable: "--font-figtree",
  display: "swap",
});

// Everything countable — timers, marks, question counts, scores — is set in
// mono with tabular figures so a ticking clock never shifts the layout.
const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cognira — Quizzes from your course material",
  description:
    "Upload your notes or slides and Cognira drafts multiple-choice questions for you to review, publish, and track.",
  keywords: ["quiz generator", "MCQ", "assessment", "teaching", "study"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // suppressHydrationWarning because the script below sets data-theme on this
    // element before React hydrates. Without it React sees the attribute as a
    // mismatch, throws away the server HTML and re-renders — which is both a
    // flash and exactly what the script exists to prevent.
    <html
      lang="en"
      className={`h-full ${figtree.variable} ${jetbrainsMono.variable}`}
      suppressHydrationWarning
    >
      <head>
        {/* Applies the saved theme before the first paint. */}
        <InlineScript
          html={
            "(function(){try{var t=localStorage.getItem('cognira-theme');" +
            "if(t==='light'||t==='dark'){document.documentElement.dataset.theme=t}}catch(e){}})()"
          }
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
