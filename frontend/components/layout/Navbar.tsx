"use client";

import { usePathname, useRouter } from "next/navigation";
import { Lock, Play } from "lucide-react";
import { SearchBar } from "../common/SearchBar";

const NAV_ITEMS = [
  { label: "Home", href: "/" },
  { label: "Browse", href: "/browse" },
  { label: "SRE", href: "/sre" },
] as const;

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();

  return (
    // Consistently transparent — a simple top-down fade for legibility, no
    // scroll-driven background switching.
    <nav className="fixed inset-x-0 top-0 z-50 flex items-center justify-between bg-gradient-to-b from-[#0a0a0f]/85 via-[#0a0a0f]/40 to-transparent px-8 py-4">
      <div className="flex items-center gap-8">
        <button
          type="button"
          className="flex items-center gap-2 text-lg font-extrabold tracking-tight"
          onClick={() => router.push("/")}
        >
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500">
            <Play className="h-4 w-4 fill-white text-white" />
          </span>
          <span>StreamSRE</span>
        </button>
        <div className="flex gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <button
                key={item.href}
                type="button"
                onClick={() => router.push(item.href)}
                className={[
                  "rounded-lg px-3 py-1.5 text-sm font-semibold transition-colors",
                  active
                    ? "bg-white/15 text-white"
                    : "bg-transparent text-white/60 hover:text-white",
                ].join(" ")}
              >
                {item.label}
              </button>
            );
          })}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <SearchBar />
        <button
          type="button"
          onClick={() => router.push("/admin")}
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/10 px-3 py-2 text-xs font-semibold text-white shadow-glow-soft transition-colors hover:bg-white/20"
        >
          <Lock className="h-4 w-4" />
          Admin
        </button>
      </div>
    </nav>
  );
}
