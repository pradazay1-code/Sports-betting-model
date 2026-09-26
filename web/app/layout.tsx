import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "The Desk",
  description: "Sports betting analysis — devig, EV, Kelly and drive-level simulation over live research.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
