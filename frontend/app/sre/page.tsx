"use client";

import { useEffect, useState } from "react";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";

type ServiceStatus = {
  name: string;
  url: string;
};

const SERVICES: ServiceStatus[] = [
  { name: "Upload API", url: "http://localhost:8000/health" },
  { name: "Beacon Collector", url: "http://localhost:8001/health" },
  { name: "Origin", url: "http://localhost:8080/health" },
];

export default function SreDashboardPage() {
  const [statuses, setStatuses] = useState<Record<string, "up" | "down" | "unknown">>({
    "Upload API": "unknown",
    "Beacon Collector": "unknown",
    Origin: "unknown",
  });

  useEffect(() => {
    const check = async () => {
      const next: Record<string, "up" | "down" | "unknown"> = { ...statuses };
      await Promise.all(
        SERVICES.map(async (service) => {
          try {
            const response = await fetch(service.url);
            next[service.name] = response.ok ? "up" : "down";
          } catch {
            next[service.name] = "down";
          }
        }),
      );
      setStatuses(next);
    };

    void check();
    const interval = setInterval(check, 15000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const grafanaUrl =
    process.env.NEXT_PUBLIC_GRAFANA_URL || "http://localhost:3000";

  return (
    <div className="min-h-screen text-white">
      <Navbar />
      <main className="px-8 pt-24 pb-16 space-y-10">
        <section>
          <h1 className="text-2xl font-bold tracking-tight">
            SRE Dashboard
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-white/70">
            High-level operational view of the StreamSRE stack. For the full
            experience, run Prometheus, Grafana, and Alertmanager using{" "}
            <code className="text-xs">make up</code>.
          </p>
        </section>
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-white/50">
            Service Health
          </h2>
          <div className="grid gap-3 md:grid-cols-3">
            {SERVICES.map((service) => {
              const state = statuses[service.name] ?? "unknown";
              const color =
                state === "up"
                  ? "bg-emerald-500"
                  : state === "down"
                    ? "bg-red-500"
                    : "bg-zinc-500";
              return (
                <div
                  key={service.name}
                  className="flex items-center justify-between rounded-xl bg-white/5 px-4 py-3"
                >
                  <span className="text-sm font-medium">{service.name}</span>
                  <span className="flex items-center gap-2 text-xs text-white/70">
                    <span className={`h-2 w-2 rounded-full ${color}`} />
                    {state.toUpperCase()}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
        <section className="space-y-4">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-white/50">
            Grafana
          </h2>
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <p className="mb-3 text-xs text-white/70">
              Open the QoE/SLO dashboards directly in Grafana.
            </p>
            <a
              href={grafanaUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center rounded-lg bg-white px-4 py-1.5 text-xs font-semibold text-black"
            >
              Open Grafana
            </a>
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
