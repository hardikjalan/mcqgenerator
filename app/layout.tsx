import type { Metadata } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Cognira — AI-Powered Adaptive Assessment Platform",
  description:
    "Cognira combines Bloom's Taxonomy, RAG-powered question generation, and real-time learning analytics to deliver intelligent, personalized assessments.",
  keywords: ["adaptive assessment", "AI", "Bloom's Taxonomy", "MCQ generator", "learning analytics"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`h-full ${inter.variable} ${spaceGrotesk.variable}`}>
      <body className="min-h-full flex flex-col antialiased bg-[#030712]">{children}</body>
    </html>
  );
}
