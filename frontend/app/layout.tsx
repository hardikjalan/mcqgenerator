import type { Metadata } from "next";
import { Figtree, JetBrains_Mono } from "next/font/google";
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
    <html lang="en" className={`h-full ${figtree.variable} ${jetbrainsMono.variable}`}>
      <head>
        {/*
          Applies the saved theme before the first paint. Without this the page
          renders in the system theme for a frame and then snaps to the chosen
          one — the flash of wrong theme. It has to be inline and blocking to
          beat paint, which is why it isn't a component.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html:
              "(function(){try{var t=localStorage.getItem('cognira-theme');" +
              "if(t==='light'||t==='dark'){document.documentElement.dataset.theme=t}}catch(e){}})()",
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
