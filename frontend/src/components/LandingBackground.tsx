// Decorative gradient blobs shown behind every page. Fixed to the viewport
// (not the document), so they stay in place and never scroll with page
// content. Rendered once by App.tsx, above all routes.
//
// Retuned for the Horizon theme: that theme gets its depth from card shadows
// sitting on a flat plane, so these are dialled well back from the original
// and tinted with the brand accent — present enough to keep the page from
// reading as dead flat, faint enough not to muddy the shadows on top.
export function LandingBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -left-20 top-10 h-72 w-72 animate-float rounded-full bg-brand-400/10 blur-3xl dark:bg-brand-500/20" />
      <div
        className="absolute -right-16 top-40 h-80 w-80 animate-float rounded-full bg-brandLinear/10 blur-3xl dark:bg-brand-400/10"
        style={{ animationDelay: "1.5s" }}
      />
    </div>
  );
}
