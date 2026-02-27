export function Footer() {
  return (
    <footer className="border-t border-white/5 px-8 py-6 text-xs text-white/40">
      <div className="flex items-center justify-between">
        <span>StreamSRE · Video Streaming Platform · SRE Portfolio Project</span>
        <div className="flex gap-4">
          {["Prometheus", "Grafana", "Alerts"].map((label) => (
            <button
              key={label}
              type="button"
              className="text-xs text-white/40 transition-colors hover:text-white/80"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </footer>
  );
}

