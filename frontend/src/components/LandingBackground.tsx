// Decorative gradient blobs shown behind every page. Fixed to the viewport
// (not the document), so they stay in place and never scroll with page
// content. Rendered once by App.tsx, above all routes.
export function LandingBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div className="absolute -left-20 top-10 h-72 w-72 animate-float rounded-full bg-brand-400/20 blur-3xl" />
      <div
        className="absolute -right-16 top-40 h-80 w-80 animate-float rounded-full bg-brand-600/15 blur-3xl"
        style={{ animationDelay: "1.5s" }}
      />
    </div>
  );
}
