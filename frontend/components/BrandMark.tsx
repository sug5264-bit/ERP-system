/**
 * WELLgreen wordmark, recreated from the official brand guideline AI file
 * (cff2db1d-__________OL.ai). The leaf glyph + two-tone wordmark sit inline
 * so the sidebar/login can render at any size without an image asset.
 *
 * Variant prop:
 *   "full"  → leaf + dark-brown WELL + green green (default)
 *   "mono"  → leaf + wordmark all in `color` (defaults to brown)
 */
"use client";

type Variant = "full" | "mono";

export default function BrandMark({
  variant = "full",
  size = 28,
  color,
  className = "",
}: {
  variant?: Variant;
  size?: number; // px height of the leaf glyph
  color?: string; // mono color override
  className?: string;
}) {
  const brandBrown = "#4B1E00";
  const brandGreen = "#87A53C";

  const wellColor = variant === "mono" ? (color ?? brandBrown) : brandBrown;
  const greenColor = variant === "mono" ? (color ?? brandBrown) : brandGreen;

  return (
    <span
      className={`inline-flex items-center gap-2 font-brand ${className}`}
      style={{ lineHeight: 1 }}
    >
      <svg
        viewBox="0 0 48 48"
        width={size}
        height={size}
        fill="none"
        stroke={greenColor}
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden
      >
        {/* Leaf body */}
        <path
          d="M8 38c0-16 12-30 32-30 0 16-12 30-32 30z"
          fill={greenColor}
          stroke="none"
        />
        {/* Mid vein */}
        <path d="M9 39 L36 12" stroke={brandBrown} strokeWidth={1.6} />
        {/* Side veins */}
        <path d="M16 33 L25 24" stroke={brandBrown} strokeWidth={1.2} />
        <path d="M22 28 L31 19" stroke={brandBrown} strokeWidth={1.2} />
      </svg>
      <span
        style={{
          fontWeight: 800,
          fontSize: size * 0.95,
          letterSpacing: "-0.02em",
        }}
      >
        <span style={{ color: wellColor }}>WELL</span>
        <span style={{ color: greenColor }}>green</span>
      </span>
    </span>
  );
}
