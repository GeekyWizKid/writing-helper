import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import Script from 'next/script';
import Footer from "./components/Footer";
import { Analytics } from '@vercel/analytics/react';

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AI 写作助手",
  description: "由先进的大语言模型驱动的智能写作助手",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh">
      <head>
        {/* Preconnect to external API endpoints for faster connections */}
        <link rel="preconnect" href="https://api.openai.com" />
        <link rel="preconnect" href="https://api.x.ai" />
        <link rel="preconnect" href="https://api.deepseek.com" />
        <link rel="dns-prefetch" href="https://api.openai.com" />
        <link rel="dns-prefetch" href="https://api.x.ai" />
        <link rel="dns-prefetch" href="https://api.deepseek.com" />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased flex flex-col min-h-screen`}>
        <Script id="cherry-studio-detection" strategy="afterInteractive">
          {`
            // 检测是否在Cherry Studio中运行
            function isInCherryStudio() {
              try {
                return window.parent !== window && 
                       window.location.ancestorOrigins && 
                       window.location.ancestorOrigins[0].includes('cherry-studio');
              } catch (e) {
                return false;
              }
            }
            
            // 根据环境调整UI
            if (isInCherryStudio()) {
              document.body.classList.add('in-cherry-studio');
              console.log('Running in Cherry Studio environment');
            } else {
              console.log('Running in standard environment');
            }
          `}
        </Script>
        <div className="flex-grow">
          {children}
        </div>
        <Footer />
        <Analytics />
      </body>
    </html>
  );
}
