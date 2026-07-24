"use client";

import { useState } from "react";
import { X } from "lucide-react";

export function SearchBar() {
  const [query, setQuery] = useState("");
  const [focused, setFocused] = useState(false);

  const width = focused || query ? "w-56" : "w-40";

  return (
    <div
      className={[
        "relative flex items-center overflow-hidden rounded-lg border border-white/15 bg-white/10 px-2 py-1 text-xs text-white transition-[width,border-color]",
        width,
        focused ? "border-white/40" : "border-white/15",
      ].join(" ")}
    >
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        placeholder="Search..."
        className="w-full bg-transparent text-xs text-white outline-none placeholder:text-white/30"
      />
      {query && (
        <button
          type="button"
          aria-label="Clear search"
          onClick={() => setQuery("")}
          className="ml-1 flex h-4 w-4 items-center justify-center rounded-full bg-white/20 text-[10px]"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}

