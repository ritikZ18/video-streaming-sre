"use client";

import { useEffect, useState } from "react";
import { Lock, LogOut } from "lucide-react";
import { Navbar } from "../../components/layout/Navbar";
import { Footer } from "../../components/layout/Footer";
import { UploadDropzone } from "../../components/upload/UploadDropzone";
import { UploadQueue } from "../../components/upload/UploadQueue";
import { AdminMovieForm } from "../../components/upload/AdminMovieForm";
import { AdminCatalog } from "../../components/admin/AdminCatalog";
import { adminLogin } from "../../lib/api";
import { isAuthed, clearAdminToken } from "../../lib/auth";

export default function AdminPage() {
  const [authed, setAuthed] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    setAuthed(isAuthed());
    setChecked(true);
  }, []);

  return (
    <div className="min-h-screen text-white">
      <Navbar />
      <main className="px-8 pt-24 pb-16">
        {!checked ? null : authed ? (
          <AdminPanel
            onLogout={() => {
              clearAdminToken();
              setAuthed(false);
            }}
          />
        ) : (
          <LoginForm onSuccess={() => setAuthed(true)} />
        )}
      </main>
      <Footer />
    </div>
  );
}

function LoginForm({ onSuccess }: { onSuccess: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const ok = await adminLogin(username, password);
      if (ok) onSuccess();
      else setError("Invalid username or password.");
    } catch {
      setError("Could not reach the API. Is the stack running?");
    } finally {
      setBusy(false);
    }
  };

  const input =
    "w-full rounded-lg border border-white/20 bg-white/5 px-3 py-2 text-sm text-white outline-none placeholder:text-white/30 focus:border-white/40";

  return (
    <div className="mx-auto mt-16 max-w-sm rounded-2xl bg-white/5 p-6">
      <div className="mb-5 flex items-center gap-3">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-white/10">
          <Lock className="h-5 w-5" />
        </span>
        <div>
          <h1 className="text-lg font-bold tracking-tight">Admin sign in</h1>
          <p className="text-xs text-white/50">Required to upload or add movies.</p>
        </div>
      </div>
      <form onSubmit={submit} className="space-y-3">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Username"
          autoComplete="username"
          className={input}
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Password"
          autoComplete="current-password"
          className={input}
        />
        <button
          type="submit"
          disabled={busy || !username || !password}
          className="w-full rounded-xl bg-white px-4 py-2.5 text-sm font-bold text-black transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p className="text-xs text-rose-400">{error}</p>}
      </form>
    </div>
  );
}

function AdminPanel({ onLogout }: { onLogout: () => void }) {
  const [files, setFiles] = useState<File[]>([]);

  const addFiles = (picked: File[]) => {
    const key = (f: File) => `${f.name}::${f.size}::${f.lastModified}`;
    setFiles((prev) => {
      const have = new Set(prev.map(key));
      const additions = picked.filter((f) => !have.has(key(f)));
      return additions.length ? [...prev, ...additions] : prev;
    });
  };

  return (
    <>
      <div className="mb-8 flex max-w-3xl items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-heading">Admin · Upload</h1>
          <p className="mt-2 text-sm text-white/70">
            Drop one or many videos. Each is uploaded, then the worker transcodes
            them to HLS + DASH one at a time.
          </p>
        </div>
        <button
          type="button"
          onClick={onLogout}
          className="inline-flex items-center gap-2 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-xs font-semibold text-white/80 hover:bg-white/10"
        >
          <LogOut className="h-4 w-4" />
          Log out
        </button>
      </div>

      <div className="grid max-w-4xl gap-6">
        <UploadDropzone count={files.length} onFilesSelected={addFiles} />
        <UploadQueue files={files} onClear={() => setFiles([])} />
      </div>

      <AdminMovieForm />

      <div className="mt-4 max-w-5xl">
        <AdminCatalog />
      </div>
    </>
  );
}
