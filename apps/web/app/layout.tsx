import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "Caseflow · Investigation workspace",
  description:
    "An accountable agent workspace for synthetic charge investigations.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
