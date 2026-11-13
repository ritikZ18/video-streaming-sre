// StreamSRE mark — concept B: play glyph + broadcast waves.
// variant="mono" renders the white outline version for tight/monochrome spots.

type LogoProps = {
  size?: number;
  variant?: "brand" | "mono";
  className?: string;
};

export function Logo({ size = 32, variant = "brand", className }: LogoProps) {
  const mono = variant === "mono";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 96 96"
      aria-hidden="true"
      className={className}
    >
      {!mono && (
        <defs>
          <linearGradient id="ssre-brand" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#5b6cff" />
            <stop offset="1" stopColor="#9333ea" />
          </linearGradient>
        </defs>
      )}
      <rect
        x="2"
        y="2"
        width="92"
        height="92"
        rx="26"
        fill={mono ? "none" : "url(#ssre-brand)"}
        stroke={mono ? "#fff" : "none"}
        strokeWidth={mono ? 4 : 0}
      />
      <path d="M36 30 L36 66 L64 48 Z" fill="#fff" />
      <path
        d="M68 34 a20 20 0 010 28"
        fill="none"
        stroke="#fff"
        strokeWidth="4.5"
        strokeLinecap="round"
        opacity="0.9"
      />
      <path
        d="M74 26 a30 30 0 010 44"
        fill="none"
        stroke="#fff"
        strokeWidth="4.5"
        strokeLinecap="round"
        opacity="0.55"
      />
    </svg>
  );
}
